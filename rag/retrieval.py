import numpy as np


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def mmr_select(query, docs, embeddings, top_k, lambda_):
    if len(docs) <= top_k:
        return docs
    query_embedding = embeddings.embed_query(query)
    doc_embeddings = embeddings.embed_documents([doc.page_content for doc in docs])

    selected, remaining = [], list(range(len(docs)))
    similarities = [cosine_similarity(query_embedding, emb) for emb in doc_embeddings]
    first = int(np.argmax(similarities))
    selected.append(first)
    remaining.remove(first)

    while len(selected) < top_k and remaining:
        best_score, best_doc = -float("inf"), None
        for idx in remaining:
            relevance = cosine_similarity(query_embedding, doc_embeddings[idx])
            max_sim = max(cosine_similarity(doc_embeddings[idx], doc_embeddings[s]) for s in selected)
            score = lambda_ * relevance - (1 - lambda_) * max_sim
            if score > best_score:
                best_score, best_doc = score, idx
        selected.append(best_doc)
        remaining.remove(best_doc)

    return [docs[i] for i in selected]


def rerank(query, docs, reranker, top_k=5):
    pairs = [(query, doc.page_content) for doc in docs]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]]


def reciprocal_rank_fusion(bm25_docs, dense_docs, k=60, top_n=50):
    scores, doc_map = {}, {}

    def add_scores(docs):
        for rank, doc in enumerate(docs):
            key = doc.page_content
            doc_map[key] = doc
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)

    add_scores(bm25_docs)
    add_scores(dense_docs)
    ranked_keys = sorted(scores, key=scores.get, reverse=True)
    return [doc_map[key] for key in ranked_keys[:top_n]]


def hybrid_retrieve(query, bm25_retriever, dense_retriever, top_n=50):
    bm25_docs = bm25_retriever.invoke(query)
    dense_docs = dense_retriever.invoke(query)
    return reciprocal_rank_fusion(bm25_docs, dense_docs, top_n=top_n)


def hyde_query(query, client):
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Write a short factual passage that would likely answer the user's question. Do not mention that it is hypothetical."},
            {"role": "user", "content": query},
        ],
        temperature=0,
    )
    return completion.choices[0].message.content