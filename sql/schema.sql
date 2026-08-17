-- Kept in sync with the emitters in index.html (embDdl/graphDdl/membershipDdl/…). Do not edit independently.

CREATE TABLE IF NOT EXISTS vector_embeddings_<datestamp>
(
    doc_id INT NOT NULL,
    content VARCHAR NOT NULL,
    token_count INT,
    char_count INT,
    embed_source VARCHAR(64),
    created_at TIMESTAMP NOT NULL,
    embedding VECTOR(64, NORMALIZE) NOT NULL,
    PRIMARY KEY (doc_id)
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


-- ---- Entity graph (see Entities → Graph in index.html) --------------------
-- Node identity is the canonical entity NAME (CHAR(64)); edges reference it.
CREATE TABLE IF NOT EXISTS graph_nodes_<datestamp> (
    node       CHAR(64)  NOT NULL,   -- NODE (grammar): canonical entity name
    label      VARCHAR[] NOT NULL,   -- LABEL: ARRAY['People'] | ARRAY['Business'] | ARRAY['Organization'] | ARRAY['Facility'] | ARRAY['Location']
    doc_ids    INT[]     NOT NULL,   -- documents the entity is stated in (post-join key)
    doc_count  INT,
    aliases    VARCHAR[],            -- merged surface variants
    block_key  CHAR(64),             -- blocking key for incremental merging
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (node)
);

CREATE TABLE IF NOT EXISTS graph_edges_<datestamp> (
    node1      CHAR(64)  NOT NULL,   -- NODE1
    node2      CHAR(64)  NOT NULL,   -- NODE2
    label      VARCHAR[] NOT NULL,   -- LABEL: ARRAY['EMBEDDED'] (similarity) or ARRAY['<PREDICATE>'] (relation)
    edge_label CHAR(32)  NOT NULL,   -- edge label (scalar): edge classifier for two-layer edges
    edge_kind  CHAR(16)  NOT NULL,   -- edge kind: 'embedded' (similarity) or 'relation' (LLM predicate)
    weight     FLOAT     NOT NULL,   -- IDW strength (0,1] for similarity; 1.0 for relations
    sum_wv     DOUBLE,               -- cumulative numerator for incremental update
    sum_w      DOUBLE,               -- cumulative denominator for incremental update
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (node1, node2, edge_label)
);

CREATE TABLE IF NOT EXISTS graph_membership_<datestamp> (
    node   CHAR(64)  NOT NULL,   -- canonical entity name
    doc_id INT       NOT NULL,   -- document ID where entity appears
    label  VARCHAR[] NOT NULL    -- ARRAY['People'] | ARRAY['Business'] | ARRAY['Organization'] | ARRAY['Facility'] | ARRAY['Location']
);

-- Insert form the app emits (ARRAY[...] literals):
INSERT INTO graph_nodes_<datestamp> (node, label, doc_ids, doc_count, aliases, block_key, created_at) VALUES
    ('Kaan Karamete', ARRAY['People'], ARRAY[1,3], 3, ARRAY['K Karamete','Kaan Karamete'], 'karamete', '2026-08-16 10:30:00');
INSERT INTO graph_edges_<datestamp> (node1, node2, label, edge_label, edge_kind, weight, sum_wv, sum_w, created_at) VALUES
    ('Acme Corp', 'Kaan Karamete', ARRAY['EMBEDDED'], 'EMBEDDED', 'embedded', 0.732000, 0.732000, 1.0, '2026-08-16 10:30:00'),
    ('Acme Corp', 'Kaan Karamete', ARRAY['WORKS_AT'], 'WORKS_AT', 'relation', 1.0, 1.0, 1.0, '2026-08-16 10:30:00');
INSERT INTO graph_membership_<datestamp> (node, doc_id, label) VALUES
    ('Kaan Karamete', 1, ARRAY['People']),
    ('Acme Corp', 1, ARRAY['Business']);

-- Promote to a native graph (strength → cost for solvers). OR REPLACE so a
-- re-run rebuilds from current tables (Kinetica has no DROP GRAPH IF EXISTS).
-- The graph name is configurable in the app (defaults to entity_graph_<datestamp>):
CREATE OR REPLACE UNDIRECTED GRAPH entity_graph_<datestamp> (
  NODES => INPUT_TABLES((SELECT * FROM graph_nodes_<datestamp>)),
  EDGES => INPUT_TABLES((SELECT node1, node2, label,
                         (1 - weight) AS WEIGHT_VALUESPECIFIED FROM graph_edges_<datestamp>)));

-- Post-join graph nodes back to the embeddings/documents via membership:
SELECT n.node, m.doc_id, e.content
FROM graph_nodes_<datestamp> n
JOIN graph_membership_<datestamp> m ON n.node = m.node
JOIN vector_embeddings_<datestamp> e ON m.doc_id = e.doc_id;
