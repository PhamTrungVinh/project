"""
Run RAGAS evaluation for rag_agent. It collects questions, answers, and contexts
from the real retrieval pipeline (rag/setup.py + rag/retrieval.py), then scores them.

Run: uv run python eval/run_rag_eval.py
"""
import os

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

from config import groq_client, embeddings
from rag.setup import build_rag_resources
from rag.retrieval import mmr_select, rerank, hybrid_retrieve, hyde_query
from eval.dataset import RAG_EVAL_DATASET
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

evaluator_llm = ChatOpenAI(
    model="nvidia/nemotron-3.5-lightning:free",
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

rag_llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=os.environ["GROQ_API"],
)

def get_rag_answer_and_contexts(query: str) -> tuple[str, list[str]]:
    """Run rag_agent's actual retrieval pipeline and return (answer, contexts)."""
    resources = build_rag_resources()
    bm25, dense, reranker = resources["bm25"], resources["dense"], resources["reranker"]

    hyde = hyde_query(query, groq_client)
    docs = hybrid_retrieve(hyde, bm25, dense, top_n=50)
    docs = rerank(query, docs, reranker, top_k=20)
    docs = mmr_select(query, docs, embeddings, top_k=5, lambda_=0.7)

    contexts = [doc.page_content for doc in docs]
    context_text = "\n\n".join(
        f"[Page {doc.metadata['page'] + 1}]\n{doc.page_content}" for doc in docs
    )

    completion = rag_llm.invoke(
        [
            {"role": "system", "content": "Only answer using the provided context. Say \"I don't have information about this\" when context is insufficient."},
            {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion:\n{query}"},
        ]
    )
    answer = completion.content
    return answer, contexts


def build_eval_dataset() -> Dataset:
    rows = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

    for item in RAG_EVAL_DATASET:
        print(f"Running: {item['question']}")
        answer, contexts = get_rag_answer_and_contexts(item["question"])

        rows["question"].append(item["question"])
        rows["answer"].append(answer)
        rows["contexts"].append(contexts)
        rows["ground_truth"].append(item["ground_truth"])

    return Dataset.from_dict(rows)


if __name__ == "__main__":
    dataset = build_eval_dataset()

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=evaluator_llm,
        embeddings=embeddings,
    )

    print("\n" + "=" * 50)
    print("RAGAS Evaluation Results")
    print("=" * 50)
    print(result)

    df = result.to_pandas()
    df.to_csv("eval/rag_eval_results.csv", index=False)
    print("\nSaved detailed results to eval/rag_eval_results.csv")