-- xVector reference schema.
-- The app generates this at runtime in ddl(); this file is documentation. If ddl()
-- changes, change this in the same commit. <datestamp> is YYYYMMDD or YYYYMMDD_HHMMSS.

CREATE TABLE IF NOT EXISTS vector_embeddings_<datestamp>
(
    doc_id INT NOT NULL,
    content VARCHAR NOT NULL,
    token_count INT,
    char_count INT,
    embed_source VARCHAR(64),
    created_at TIMESTAMP NOT NULL,
    embedding VECTOR(64, NORMALIZE) NOT NULL
);

-- NORMALIZE gives each inserted vector an L2 magnitude of 1. Drop it if you need the
-- original magnitudes; cosine results are unaffected either way.

-- Automatically maintained as rows change. CAGRA is faster to query but needs a manual
-- refresh, which suits a table that stops being written to.
ALTER TABLE vector_embeddings_<datestamp> ADD HNSW INDEX (embedding);


-- Insert form the app emits, batched at 50 rows per statement.
INSERT INTO vector_embeddings_<datestamp>
(doc_id, content, token_count, char_count, embed_source, created_at, embedding)
VALUES
    (1, 'first paragraph', 24, 141, 'local-hash-64', '2026-08-16 10:30:00', '[0.031,-0.118,...]'),
    (2, 'second paragraph', 31, 190, 'local-hash-64', '2026-08-16 10:30:00', '[-0.204,0.077,...]');


-- Nearest neighbours to a query vector. TOP goes after SELECT.
SELECT TOP 5
    doc_id,
    content,
    COSINE_DISTANCE(embedding, '[0.031,-0.118,...]') AS distance
FROM vector_embeddings_<datestamp>
ORDER BY distance;

-- Operator shorthand: <-> is L2_DISTANCE, <=> is COSINE_DISTANCE, <#> is DOT_PRODUCT.
SELECT TOP 5 doc_id, embedding <=> VECTOR('[0.031,-0.118,...]', 64) AS distance
FROM vector_embeddings_<datestamp>
ORDER BY distance;

-- Nearest neighbours to a row already in the table.
SELECT TOP 5 t.doc_id, t.content, COSINE_DISTANCE(t.embedding, s.seed) AS distance
FROM
    vector_embeddings_<datestamp> t,
    (SELECT embedding AS seed FROM vector_embeddings_<datestamp> WHERE doc_id = 1) s
WHERE t.doc_id <> 1
ORDER BY distance;

-- Sanity checks after a load.
SELECT COUNT(*) AS rows, MIN(created_at) AS first_write FROM vector_embeddings_<datestamp>;
SELECT doc_id, SIZE(embedding) AS dims, L2_NORM(embedding) AS magnitude
FROM vector_embeddings_<datestamp>;
