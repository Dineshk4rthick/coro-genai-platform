import hashlib
import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import OpenAI

from ingestion.chunking import chunk_markdown
from ingestion.index import INDEX_NAME, build_index


EMBEDDING_MODEL = "text-embedding-3-small"


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def main() -> None:
    storage_url = required_env("STORAGE_ACCOUNT_URL")
    search_endpoint = required_env("SEARCH_ENDPOINT")
    foundry_endpoint = required_env("FOUNDRY_ENDPOINT")
    container_name = os.getenv("BLOB_CONTAINER", "policies")

    credential = DefaultAzureCredential()

    # Foundry's OpenAI-compatible endpoint for embeddings.
    token_provider = get_bearer_token_provider(
        credential,
        "https://ai.azure.com/.default",
    )

    embedding_client = OpenAI(
        base_url=f"{foundry_endpoint.rstrip('/')}/openai/v1/",
        api_key=token_provider(),
    )

    blob_service = BlobServiceClient(
        account_url=storage_url,
        credential=credential,
    )
    container = blob_service.get_container_client(container_name)

    index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=credential,
    )
    index_client.create_or_update_index(build_index())

    search_client = SearchClient(
        endpoint=search_endpoint,
        index_name=INDEX_NAME,
        credential=credential,
    )

    documents = []

    for blob in container.list_blobs():
        if not blob.name.lower().endswith(".md"):
            continue

        text = container.download_blob(blob.name).readall().decode("utf-8")
        chunks = chunk_markdown(text)

        for chunk_number, chunk in enumerate(chunks):
            documents.append({
                "id": hashlib.sha256(
                    f"{blob.name}:{chunk_number}".encode("utf-8")
                ).hexdigest(),
                "source": blob.name,
                "chunk_index": chunk_number,
                "embedding_model": EMBEDDING_MODEL,
                "content": chunk,
            })

    if not documents:
        raise RuntimeError(
            f"No Markdown files found in blob container '{container_name}'."
        )

    # Generate embeddings in batches.
    batch_size = 32

    for start in range(0, len(documents), batch_size):
        batch = documents[start:start + batch_size]

        response = embedding_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[doc["content"] for doc in batch],
        )

        for doc, result in zip(batch, response.data):
            doc["embedding"] = result.embedding

        search_client.upload_documents(documents=batch)
        print(f"Uploaded {min(start + len(batch), len(documents))}"
              f"/{len(documents)} chunks")

    # Remove chunks left over from earlier chunking strategies or deleted files,
    # so the index always matches the current documents exactly.
    keep_ids = {doc["id"] for doc in documents}
    existing = [r["id"] for r in search_client.search(search_text="*", select=["id"])]
    stale = [{"id": i} for i in existing if i not in keep_ids]
    if stale:
        search_client.delete_documents(documents=stale)
        print(f"Removed {len(stale)} stale chunks")

    print(
        f"Finished: indexed {len(documents)} chunks "
        f"in '{INDEX_NAME}'."
    )


if __name__ == "__main__":
    main()
