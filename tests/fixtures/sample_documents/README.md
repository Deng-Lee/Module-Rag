# Sample Documents for Testing

This directory contains sample documents used for testing the RAG pipeline.

## Contents

- `sample.txt` - A minimal plain-text sample used for negative tests; the default ingest pipeline does not load `.txt`

## Usage

These documents are used by integration and e2e tests to verify:
- Document loading
- Text splitting
- Embedding generation
- Vector storage operations
