# MongoDB support

Forge 0.3 adds a document-resource layer alongside SQLAlchemy relational resources.

The implementation uses the modern **PyMongo Async API** (`AsyncMongoClient`), not Motor. MongoDB's current driver documentation recommends PyMongo Async as the Motor replacement.

## Configuration

```json
{
  "mongo_databases": {
    "documents": {
      "uri": "$env:MONGODB_URL",
      "database": "my_app",
      "max_pool_size": 100,
      "min_pool_size": 5,
      "server_selection_timeout_ms": 5000
    }
  },
  "mongo_resources": [
    {
      "database": "documents",
      "collection": "profiles",
      "path": "documents/profiles",
      "writable_fields": ["user_id", "display_name", "settings"],
      "allowed_filters": ["user_id"],
      "allowed_sort": ["user_id"]
    }
  ]
}
```

Generated routes use the same project authentication, permissions, rate limiting, cache namespace isolation and tenant model as relational resources.

## Supported operations

- list
- count
- read by `_id`
- create
- update
- delete / soft delete
- tenant field enforcement
- basic safe filter operators
- cache + generation invalidation
- JSON Schema validation on create/update

ObjectId values are serialized to strings in API responses.

## Relational vs MongoDB

Use PostgreSQL/MySQL when transactions, relational constraints, money/accounting and joins are central. MongoDB fits flexible documents, settings, telemetry-like documents and data whose schema evolves rapidly. Do not choose MongoDB merely to avoid designing data models.

See `examples/mongodb-fragment.json`.
