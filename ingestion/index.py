from azure.search.documents.indexes.models import (
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)


INDEX_NAME = "contoso-policy-chunks"
EMBEDDING_DIMENSIONS = 1536


def build_index() -> SearchIndex:
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
        ),
        SearchableField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="embedding_model",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
        ),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(
                SearchFieldDataType.Single
            ),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="policy-vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="policy-hnsw")
        ],
        profiles=[
            VectorSearchProfile(
                name="policy-vector-profile",
                algorithm_configuration_name="policy-hnsw",
            )
        ],
    )

    return SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )
