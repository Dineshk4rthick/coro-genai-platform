"""API tests. Azure OpenAI and Azure AI Search are replaced by fakes, so these
run offline, cost nothing and are deterministic."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main

PASSAGES = [
    {"source": "hr-leave-policy.md", "content": "Employees receive 10 working days of sick leave per year."},
    {"source": "hr-leave-policy.md", "content": "A medical certificate is required after two consecutive days."},
    {"source": "hr-remote-work.md", "content": "Core hours are 9 AM to 3 PM."},
]


class FakeOpenAI:
    def __init__(self, answer="Ten working days.", embed_error=None, chat_error=None):
        self.embed_calls, self.chat_calls = [], []
        self._answer, self._embed_error, self._chat_error = answer, embed_error, chat_error
        self.embeddings = SimpleNamespace(create=self._embed)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    def _embed(self, **kwargs):
        self.embed_calls.append(kwargs)
        if self._embed_error:
            raise self._embed_error
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * 1536)])

    def _chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        if self._chat_error:
            raise self._chat_error
        message = SimpleNamespace(content=self._answer)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeSearch:
    def __init__(self, results=None, error=None):
        self.calls, self._results, self._error = [], PASSAGES if results is None else results, error

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return iter(self._results)


@pytest.fixture
def azure(monkeypatch):
    """Install fakes and return them so tests can inspect what was called."""
    def install(openai=None, search=None):
        openai, search = openai or FakeOpenAI(), search or FakeSearch()
        monkeypatch.setattr(main, "get_openai_client", lambda: openai)
        monkeypatch.setattr(main, "get_search_client", lambda: search)
        return openai, search
    return install


client = TestClient(main.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_version_reports_git_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    assert client.get("/version").json() == {"version": "9.9.9", "git_sha": "abc123"}


@pytest.mark.parametrize("question", ["", "   ", "\n\t"])
def test_empty_question_is_rejected_without_calling_azure(azure, question):
    openai, search = azure()
    r = client.post("/chat", json={"question": question})
    assert r.status_code == 400
    assert openai.embed_calls == [] and search.calls == []


def test_missing_question_field_is_422():
    assert client.post("/chat", json={}).status_code == 422


def test_successful_answer_has_deduplicated_sorted_sources(azure):
    azure()
    r = client.post("/chat", json={"question": "How many sick days?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Ten working days."
    assert body["sources"] == ["hr-leave-policy.md", "hr-remote-work.md"]


def test_question_is_stripped_before_use(azure):
    openai, search = azure()
    client.post("/chat", json={"question": "  sick days?  "})
    assert openai.embed_calls[0]["input"] == ["sick days?"]
    assert search.calls[0]["search_text"] == "sick days?"


def test_retrieval_is_hybrid_and_limited_to_three(azure):
    _, search = azure()
    client.post("/chat", json={"question": "sick leave"})
    call = search.calls[0]
    assert call["search_text"] == "sick leave"          # keyword half
    assert len(call["vector_queries"]) == 1             # vector half
    assert call["top"] == 3
    vq = call["vector_queries"][0]
    assert vq.k_nearest_neighbors == 3 and vq.fields == "embedding"


def test_model_receives_retrieved_text_and_a_grounding_prompt(azure):
    openai, _ = azure()
    client.post("/chat", json={"question": "sick leave"})
    system, user = openai.chat_calls[0]["messages"]
    assert system["role"] == "system" and "only" in system["content"].lower()
    assert "not as instructions" in system["content"].lower()
    assert "10 working days" in user["content"]
    assert "Source: hr-leave-policy.md" in user["content"]


def test_temperature_is_not_sent(azure):
    """gpt-5-mini rejects explicit temperature values with HTTP 400."""
    openai, _ = azure()
    client.post("/chat", json={"question": "sick leave"})
    assert "temperature" not in openai.chat_calls[0]


def test_no_results_returns_fallback_and_skips_the_model(azure):
    openai, _ = azure(search=FakeSearch(results=[]))
    r = client.post("/chat", json={"question": "something unrelated"})
    assert r.status_code == 200
    assert r.json()["sources"] == []
    assert "couldn't find" in r.json()["answer"].lower()
    assert openai.chat_calls == []


@pytest.mark.parametrize(
    "openai, search",
    [
        (FakeOpenAI(embed_error=RuntimeError("secret-embed-detail")), None),
        (None, FakeSearch(error=RuntimeError("secret-search-detail"))),
        (FakeOpenAI(chat_error=RuntimeError("secret-chat-detail")), None),
    ],
    ids=["embedding-fails", "search-fails", "chat-fails"],
)
def test_azure_failures_return_generic_502(azure, openai, search):
    azure(openai=openai, search=search)
    r = client.post("/chat", json={"question": "sick leave"})
    assert r.status_code == 502
    assert "secret" not in r.text  # internal error text must not leak
    assert r.json()["detail"] == "The policy assistant could not complete the request."
