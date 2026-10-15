"""DuckDB schema, applied as ordered migrations.

Temporal rows: ``records``, ``cells`` and (later) entity tables carry ``version_from`` /
``version_to``. A row is current when ``version_to IS NULL``; the state at version *v* is
``version_from <= v AND (version_to IS NULL OR version_to > v)``. Nothing is ever deleted,
which is what makes provenance, undo and "restore this version" cheap and safe.
"""

MIGRATIONS: list[str] = [
    # 1: core tables
    """
    CREATE SEQUENCE seq_id START 1;
    CREATE SEQUENCE seq_version START 1;

    CREATE TABLE workspaces (
        id          BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        name        VARCHAR NOT NULL,
        is_demo     BOOLEAN NOT NULL DEFAULT FALSE,
        created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp
    );

    CREATE TABLE versions (
        id            BIGINT PRIMARY KEY DEFAULT nextval('seq_version'),
        workspace_id  BIGINT NOT NULL,
        kind          VARCHAR NOT NULL,  -- upload|manual_edit|match_decision|undo|restore
        message       VARCHAR,
        created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
    );

    CREATE TABLE uploads (
        id            BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        workspace_id  BIGINT NOT NULL,
        version_id    BIGINT,
        filename      VARCHAR NOT NULL,
        sha256        VARCHAR NOT NULL,
        size_bytes    BIGINT NOT NULL,
        status        VARCHAR NOT NULL,     -- processing | done | failed
        error_code    VARCHAR,
        created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
    );

    -- One row per sheet (CSV files have exactly one).
    CREATE TABLE upload_tables (
        id           BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        upload_id    BIGINT NOT NULL,
        sheet        VARCHAR,
        header_row   INTEGER,
        dataset_id   BIGINT,
        meta         JSON
    );

    -- The source exactly as read. Immutable.
    CREATE TABLE raw_rows (
        table_id     BIGINT NOT NULL,
        row_index    INTEGER NOT NULL,
        cells        VARCHAR[] NOT NULL,
        skip_reason  VARCHAR,               -- NULL for data rows
        PRIMARY KEY (table_id, row_index)
    );

    CREATE TABLE source_columns (
        table_id     BIGINT NOT NULL,
        col_index    INTEGER NOT NULL,
        header       VARCHAR NOT NULL,
        role         VARCHAR NOT NULL,
        confidence   DOUBLE NOT NULL,
        engine       VARCHAR NOT NULL,
        reasons      JSON NOT NULL,
        field_id     BIGINT,
        PRIMARY KEY (table_id, col_index)
    );

    CREATE TABLE datasets (
        id            BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        workspace_id  BIGINT NOT NULL,
        name          VARCHAR NOT NULL,
        created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
    );

    CREATE TABLE fields (
        id          BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        dataset_id  BIGINT NOT NULL,
        key         VARCHAR NOT NULL,       -- "date", "party", "description:urun"
        label       VARCHAR NOT NULL,       -- first header seen for this field
        role        VARCHAR NOT NULL,
        dtype       VARCHAR NOT NULL,       -- text | number | date
        position    INTEGER NOT NULL,
        pii         VARCHAR,                -- phone | tckn | email
        UNIQUE (dataset_id, key)
    );

    CREATE TABLE records (
        id            BIGINT NOT NULL,
        dataset_id    BIGINT NOT NULL,
        table_id      BIGINT NOT NULL,
        row_index     INTEGER NOT NULL,
        status        VARCHAR NOT NULL,     -- active | duplicate
        duplicate_of  BIGINT,
        version_from  BIGINT NOT NULL,
        version_to    BIGINT
    );

    CREATE TABLE cells (
        record_id     BIGINT NOT NULL,
        field_id      BIGINT NOT NULL,
        value_text    VARCHAR,
        value_num     DECIMAL(18, 4),
        value_date    DATE,
        raw_value     VARCHAR,
        src_cols      INTEGER[] NOT NULL,
        version_from  BIGINT NOT NULL,
        version_to    BIGINT
    );

    CREATE TABLE transformations (
        id                 BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        version_id         BIGINT NOT NULL,
        table_id           BIGINT NOT NULL,
        record_id          BIGINT,
        field_id           BIGINT,
        kind               VARCHAR NOT NULL,
        before_value       VARCHAR,
        after_value        VARCHAR,
        confidence         DOUBLE NOT NULL,
        detail             JSON NOT NULL,
        undone_in_version  BIGINT
    );

    CREATE INDEX idx_records_dataset ON records (dataset_id);
    CREATE INDEX idx_cells_record ON cells (record_id);
    CREATE INDEX idx_transformations_table ON transformations (table_id);
    """,
    # 2: entity resolution
    """
    -- A real-world party (customer/supplier). Membership is derived from records plus the
    -- user's decisions, so the canonical name is recomputed on every resolution run.
    CREATE TABLE entities (
        id               BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        workspace_id     BIGINT NOT NULL,
        canonical_name   VARCHAR NOT NULL,
        created_version  BIGINT NOT NULL
    );

    CREATE TABLE entity_members (
        record_id     BIGINT NOT NULL,
        entity_id     BIGINT NOT NULL,
        version_from  BIGINT NOT NULL,
        version_to    BIGINT
    );

    -- "Are these two the same?" cards. pair_key identifies the two name profiles, so a card
    -- keeps its id across re-runs and a skipped card does not come back.
    CREATE TABLE match_candidates (
        id               BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        workspace_id     BIGINT NOT NULL,
        pair_key         VARCHAR NOT NULL,
        profile_a        VARCHAR NOT NULL,
        profile_b        VARCHAR NOT NULL,
        entity_a         BIGINT NOT NULL,
        entity_b         BIGINT NOT NULL,
        score            DOUBLE NOT NULL,
        evidence         JSON NOT NULL,
        status           VARCHAR NOT NULL,  -- pending|accepted|rejected|skipped|superseded
        created_version  BIGINT NOT NULL,
        decided_version  BIGINT,
        UNIQUE (workspace_id, pair_key)
    );

    -- Human decisions, applied as must-link / cannot-link constraints on every later run.
    CREATE TABLE match_decisions (
        id               BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        workspace_id     BIGINT NOT NULL,
        candidate_id     BIGINT,
        profile_a        VARCHAR NOT NULL,
        profile_b        VARCHAR NOT NULL,
        decision         VARCHAR NOT NULL,  -- same | different | skip
        version_id       BIGINT NOT NULL,
        revoked_version  BIGINT
    );

    CREATE INDEX idx_entity_members_record ON entity_members (record_id);
    CREATE INDEX idx_entity_members_entity ON entity_members (entity_id);
    """,
    # 3: analytics: structured version details, natural-language query log
    """
    ALTER TABLE versions ADD COLUMN details JSON;

    CREATE TABLE query_log (
        id            BIGINT PRIMARY KEY DEFAULT nextval('seq_id'),
        workspace_id  BIGINT NOT NULL,
        dataset_id    BIGINT,
        question      VARCHAR NOT NULL,
        sql           VARCHAR,
        engine        VARCHAR NOT NULL,     -- rules | llm | none
        ok            BOOLEAN NOT NULL,
        error_code    VARCHAR,
        row_count     INTEGER,
        duration_ms   INTEGER NOT NULL,
        created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
    );
    """,
]
