-- Extensions required by DATABASE_SCHEMA.md §1.
-- Only what the approved schema requires: uuid-ossp/pgcrypto (id generation),
-- vector (pgvector, heritage RAG + personalization embeddings),
-- postgis (geography type, geofencing / nearby search).
-- No other extensions are installed.

create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;
create extension if not exists vector;
create extension if not exists postgis;
