from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ...interfaces.evaluator.evaluator import EvalCaseResult


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


@contextmanager
def _temp_env(pairs: dict[str, str]) -> Any:
    prev: dict[str, str | None] = {k: os.environ.get(k) for k in pairs}
    try:
        for k, v in pairs.items():
            os.environ[k] = v
        yield
    finally:
        for k, old in prev.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


@dataclass
class RagasAdapter:
    """Optional adapter: delegates metric computation to RAGAS (if installed).

    Notes:
    - RAGAS internally needs an LLM/embeddings backend. We configure OpenAI-compatible
      backends via environment variables when `api_key/base_url` are provided.
    - This keeps the rest of the pipeline unchanged and avoids hard-coding an SDK.
    """

    provider_id: str = "ragas"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    endpoint_key: str | None = None  # accepted for config compatibility (resolved upstream)

    def evaluate_case(self, case: Any, run_output: dict[str, Any]) -> EvalCaseResult:
        try:
            from datasets import Dataset  # type: ignore
            from ragas import evaluate  # type: ignore
            from ragas.metrics import answer_relevancy, faithfulness  # type: ignore
        except Exception:
            return EvalCaseResult(
                case_id=_case_id(case),
                metrics={},
                artifacts={
                    "error": "dependency_missing",
                    "dependency": "ragas",
                    "reason": "ragas_not_installed",
                },
            )
        query = _case_query(case)
        answer = run_output.get("answer") or ""
        contexts = run_output.get("retrieved_texts") or []
        if not isinstance(contexts, list):
            contexts = [str(contexts)]
        expected_answer = _case_expected_answer(case)

        payload: dict[str, Any] = {
            "question": [query],
            "answer": [answer],
            "contexts": [contexts],
        }
        if expected_answer:
            payload["ground_truth"] = [expected_answer]

        dataset = Dataset.from_dict(payload)
        env: dict[str, str] = {}
        if isinstance(self.api_key, str) and self.api_key:
            env["OPENAI_API_KEY"] = self.api_key
        if isinstance(self.base_url, str) and self.base_url:
            env["OPENAI_BASE_URL"] = self.base_url
        # Some stacks read this; harmless if ignored.
        if isinstance(self.model, str) and self.model:
            env["OPENAI_MODEL"] = self.model
        if isinstance(self.embedding_model, str) and self.embedding_model:
            env["OPENAI_EMBEDDING_MODEL"] = self.embedding_model

        try:
            # Prefer constructing an explicit ragas LLM using provided api_key/base_url
            llm_obj = None
            try:
                from openai import OpenAI  # type: ignore
                from ragas.llms import llm_factory  # type: ignore

                client_args: dict[str, str] = {}
                if isinstance(self.api_key, str) and self.api_key:
                    client_args["api_key"] = self.api_key
                if isinstance(self.base_url, str) and self.base_url:
                    client_args["base_url"] = self.base_url
                # Only create a client when we have at least one connection parameter.
                if client_args:
                    client = OpenAI(**client_args)
                    llm_obj = llm_factory(self.model or "gpt-4o-mini", client=client)
            except Exception:
                llm_obj = None

            # Try to construct a ragas-compatible embeddings object backed by the
            # same OpenAI-compatible client. Ragas expects an object exposing
            # methods like `embed_query` and `embed_documents`.
            emb_obj = None
            try:
                embedding_client = None
                embedding_model = (
                    self.embedding_model
                    or os.environ.get("OPENAI_EMBEDDING_MODEL")
                    or os.environ.get("OPENAI_MODEL")
                    or "text-embedding-3-small"
                )
                embedding_client_args: dict[str, str] = {}
                if isinstance(self.embedding_api_key, str) and self.embedding_api_key:
                    embedding_client_args["api_key"] = self.embedding_api_key
                elif isinstance(self.api_key, str) and self.api_key:
                    embedding_client_args["api_key"] = self.api_key
                if isinstance(self.embedding_base_url, str) and self.embedding_base_url:
                    embedding_client_args["base_url"] = self.embedding_base_url
                elif isinstance(self.base_url, str) and self.base_url:
                    embedding_client_args["base_url"] = self.base_url

                if embedding_client_args:
                    from openai import OpenAI  # type: ignore

                    embedding_client = OpenAI(**embedding_client_args)
                elif 'client' in locals():
                    embedding_client = client

                if embedding_client is not None:
                    class _RagasEmbeddings:
                        def __init__(self, client, model: str):
                            self._client = client
                            self._model = model

                        def embed_query(self, text: str):
                            resp = self._client.embeddings.create(model=self._model, input=text)
                            # OpenAI response: data[0].embedding
                            return resp.data[0].embedding

                        def embed_documents(self, texts: list[str]):
                            resp = self._client.embeddings.create(model=self._model, input=texts)
                            return [d.embedding for d in resp.data]

                        # ragas may call other helper names; provide a common alias
                        def embed(self, texts: list[str]):
                            return self.embed_documents(texts)

                    emb_obj = _RagasEmbeddings(embedding_client, embedding_model)
            except Exception:
                emb_obj = None

            with _temp_env(env) if env else _temp_env({}):
                if llm_obj is not None:
                    if emb_obj is not None:
                        result = evaluate(
                            dataset,
                            metrics=[faithfulness, answer_relevancy],
                            llm=llm_obj,
                            embeddings=emb_obj,
                            show_progress=False,
                        )
                    else:
                        result = evaluate(
                            dataset,
                            metrics=[faithfulness, answer_relevancy],
                            llm=llm_obj,
                            show_progress=False,
                        )
                else:
                    if emb_obj is not None:
                        result = evaluate(
                            dataset,
                            metrics=[faithfulness, answer_relevancy],
                            embeddings=emb_obj,
                            show_progress=False,
                        )
                    else:
                        result = evaluate(
                            dataset,
                            metrics=[faithfulness, answer_relevancy],
                            show_progress=False,
                        )
        except Exception as exc:
            return EvalCaseResult(
                case_id=_case_id(case),
                metrics={},
                artifacts={
                    "error": "backend_error",
                    "backend": "ragas",
                    "stage": "ragas.evaluate",
                    "exc_type": type(exc).__name__,
                    "message": str(exc),
                    "model": self.model or "",
                    "embedding_model": self.embedding_model or "",
                    "base_url": self.base_url or "",
                    "embedding_base_url": self.embedding_base_url or "",
                    "hint": (
                        "set OPENAI_API_KEY (or configure evaluator api_key via "
                        "model_endpoints)"
                    ),
                },
            )

        metrics: dict[str, float] = {}
        extracted = _extract_ragas_scores(result)
        if "faithfulness" in extracted:
            metrics["ragas.faithfulness"] = _safe_float(extracted["faithfulness"])
        if "answer_relevancy" in extracted:
            metrics["ragas.answer_relevancy"] = _safe_float(extracted["answer_relevancy"])

        return EvalCaseResult(
            case_id=_case_id(case),
            metrics=metrics,
            artifacts={
                "ragas_metrics": list(extracted.keys()),
                "model": self.model or "",
                "embedding_model": self.embedding_model or "",
                "embedding_base_url": self.embedding_base_url or "",
            },
        )


def _extract_ragas_scores(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    if hasattr(result, "to_pandas"):
        try:
            df = result.to_pandas()
            if df is not None and len(df.index) > 0:
                row = df.iloc[0].to_dict()
                return {k: row[k] for k in row.keys()}
        except Exception:
            pass
    if hasattr(result, "dataframe"):
        try:
            df = result.dataframe
            if df is not None and len(df.index) > 0:
                row = df.iloc[0].to_dict()
                return {k: row[k] for k in row.keys()}
        except Exception:
            pass
    if hasattr(result, "scores"):
        try:
            return dict(result.scores)  # type: ignore[arg-type]
        except Exception:
            pass
    return {}


def _case_id(case: Any) -> str:
    if isinstance(case, dict):
        return str(case.get("case_id") or "unknown")
    return str(getattr(case, "case_id", "unknown"))


def _case_query(case: Any) -> str:
    if isinstance(case, dict):
        return str(case.get("query") or "")
    return str(getattr(case, "query", "") or "")


def _case_expected_answer(case: Any) -> str | None:
    if isinstance(case, dict):
        value = case.get("expected_answer")
    else:
        value = getattr(case, "expected_answer", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
