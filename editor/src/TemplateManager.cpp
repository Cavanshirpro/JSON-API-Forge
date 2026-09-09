#include "TemplateManager.hpp"

#include "DocumentCodec.hpp"
#include "GraphModel.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QUuid>

namespace {
bool fail(QString *errorMessage, const QString &message)
{
    if (errorMessage != nullptr) {
        *errorMessage = message;
    }
    return false;
}

bool writeJson(const QDir &root, const QString &relative, const QJsonObject &object, QString *errorMessage)
{
    return DocumentCodec::saveAtomically(root.filePath(relative), DocumentCodec::prettyJson(object), errorMessage);
}

QJsonObject graphFor(const ProjectTemplate &definition)
{
    GraphModel graph;
    graph.setDocument(GraphModel::emptyDocument(QStringLiteral("config/50-operations.json")));
    const auto request = graph.addNode(
        QStringLiteral("request.input"), QStringLiteral("Request Input"), QPointF(0.0, 0.0),
        QJsonObject{{QStringLiteral("method"), QStringLiteral("GET")},
                    {QStringLiteral("input_schema"),
                     QJsonObject{{QStringLiteral("type"), QStringLiteral("object")},
                                 {QStringLiteral("additionalProperties"), false},
                                 {QStringLiteral("properties"), QJsonObject{}}}}});
    const auto policy = graph.addNode(
        QStringLiteral("auth.policy"), QStringLiteral("Authorization Policy"), QPointF(300.0, 0.0),
        QJsonObject{{QStringLiteral("permission"), definition.permissionPrefix + QStringLiteral(".analytics")},
                    {QStringLiteral("public"), false}});
    const auto query = graph.addNode(
        QStringLiteral("data.query"), QStringLiteral("Aggregate by status"), QPointF(600.0, 0.0),
        QJsonObject{{QStringLiteral("sql"),
                     QStringLiteral("SELECT status, COUNT(*) AS records, COALESCE(SUM(amount), 0) AS total_amount FROM %1 GROUP BY status ORDER BY status")
                         .arg(definition.table)},
                    {QStringLiteral("mode"), QStringLiteral("fetch_all")},
                    {QStringLiteral("params"), QJsonObject{}},
                    {QStringLiteral("result_name"), QStringLiteral("summary")},
                    {QStringLiteral("max_rows"), 100}});
    const auto operation = graph.addNode(
        QStringLiteral("operation.call"), QStringLiteral("Forge Operation"), QPointF(900.0, 0.0),
        QJsonObject{{QStringLiteral("name"), definition.operationName},
                    {QStringLiteral("method"), QStringLiteral("GET")},
                    {QStringLiteral("database"), QStringLiteral("primary")},
                    {QStringLiteral("idempotency"), false},
                    {QStringLiteral("summary"), QStringLiteral("Status and amount rollup generated from the project graph")}});
    const auto response = graph.addNode(QStringLiteral("response.output"), QStringLiteral("Response"), QPointF(1200.0, 0.0),
                                        QJsonObject{{QStringLiteral("status_code"), 200}});
    QString ignored;
    graph.connectNodes(request, QStringLiteral("exec"), policy, QStringLiteral("exec"), &ignored);
    graph.connectNodes(policy, QStringLiteral("exec"), query, QStringLiteral("exec"), &ignored);
    graph.connectNodes(query, QStringLiteral("exec"), operation, QStringLiteral("exec"), &ignored);
    graph.connectNodes(operation, QStringLiteral("exec"), response, QStringLiteral("exec"), &ignored);
    return graph.document();
}
} // namespace

QList<ProjectTemplate> TemplateManager::templates(QString *errorMessage)
{
    QFile file(QStringLiteral(":/templates/catalog.json"));
    if (!file.open(QIODevice::ReadOnly) || file.size() > 256 * 1024) {
        fail(errorMessage, QStringLiteral("The embedded project template catalog is unavailable."));
        return {};
    }
    QJsonParseError parseError;
    const auto document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        fail(errorMessage, QStringLiteral("The embedded project template catalog is invalid."));
        return {};
    }
    static const QRegularExpression IdPattern(QStringLiteral(R"(^[a-z0-9]+(?:[._-][a-z0-9]+)*$)"));
    static const QRegularExpression PathPattern(QStringLiteral(R"(^[a-z0-9]+(?:[._/-][a-z0-9]+)*$)"));
    QList<ProjectTemplate> result;
    for (const auto &value : document.object().value(QStringLiteral("templates")).toArray()) {
        const auto object = value.toObject();
        ProjectTemplate definition{object.value(QStringLiteral("id")).toString(),
                                   object.value(QStringLiteral("name")).toString(),
                                   object.value(QStringLiteral("category")).toString(),
                                   object.value(QStringLiteral("description")).toString(),
                                   object.value(QStringLiteral("entity")).toString(),
                                   object.value(QStringLiteral("table")).toString(),
                                   object.value(QStringLiteral("path")).toString(),
                                   object.value(QStringLiteral("permission_prefix")).toString(),
                                   object.value(QStringLiteral("operation_name")).toString(),
                                   object.value(QStringLiteral("default_status")).toString()};
        if (!IdPattern.match(definition.id).hasMatch() || definition.name.isEmpty() || definition.description.isEmpty()
            || !IdPattern.match(definition.table).hasMatch() || !PathPattern.match(definition.path).hasMatch()
            || !IdPattern.match(definition.permissionPrefix).hasMatch() || !IdPattern.match(definition.operationName).hasMatch()
            || definition.entity.isEmpty() || definition.defaultStatus.isEmpty()) {
            fail(errorMessage, QStringLiteral("Template catalog entry '%1' violates the embedded safety contract.").arg(definition.id));
            return {};
        }
        result.append(definition);
    }
    if (result.size() < 6) {
        fail(errorMessage, QStringLiteral("The embedded project template catalog is incomplete."));
        return {};
    }
    return result;
}

bool TemplateManager::createProject(const ProjectTemplate &definition, const QString &workspaceRoot,
                                    const QString &directoryName, const QString &slug, QString *errorMessage)
{
    static const QRegularExpression DirectoryPattern(QStringLiteral(R"(^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$)"));
    static const QRegularExpression SlugPattern(QStringLiteral(R"(^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$)"));
    if (!DirectoryPattern.match(directoryName).hasMatch() || !SlugPattern.match(slug).hasMatch()) {
        return fail(errorMessage, QStringLiteral("Directory or slug does not satisfy the Forge identifier policy."));
    }
    const QFileInfo rootInfo(workspaceRoot);
    if (!rootInfo.isDir() || rootInfo.isSymLink()) {
        return fail(errorMessage, QStringLiteral("Choose a regular local workspace directory."));
    }
    QDir root(rootInfo.canonicalFilePath());
    if (QFileInfo::exists(root.filePath(directoryName))) {
        return fail(errorMessage, QStringLiteral("The project target already exists."));
    }
    const auto stagingName = QStringLiteral(".forge-template-%1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces));
    if (!root.mkpath(stagingName)) {
        return fail(errorMessage, QStringLiteral("Could not create a staging directory in the workspace."));
    }
    QDir staging(root.filePath(stagingName));
    auto cleanup = [&staging] { staging.removeRecursively(); };
    if (!staging.mkpath(QStringLiteral("config")) || !staging.mkpath(QStringLiteral("graphs"))
        || !staging.mkpath(QStringLiteral("hooks"))) {
        cleanup();
        return fail(errorMessage, QStringLiteral("Could not create the project directory structure."));
    }

    const auto environmentPrefix = QString(slug).toUpper().replace(u'-', u'_');
    const QJsonObject manifest{{QStringLiteral("$schema"), QStringLiteral("../../schemas/manifest.schema.json")},
                               {QStringLiteral("slug"), slug},
                               {QStringLiteral("name"), definition.name},
                               {QStringLiteral("version"), QStringLiteral("1.0.0")},
                               {QStringLiteral("api_prefix"), QStringLiteral("/api/%1/v1").arg(slug)},
                               {QStringLiteral("docs_enabled"), true},
                               {QStringLiteral("audit_enabled"), true}};
    const QJsonObject databases{
        {QStringLiteral("$schema"), QStringLiteral("../../../schemas/fragment.schema.json")},
        {QStringLiteral("databases"),
         QJsonObject{{QStringLiteral("primary"),
                      QJsonObject{{QStringLiteral("url"),
                                   QStringLiteral("$env:%1_DATABASE_URL:-sqlite+aiosqlite:///./data/%2.db")
                                       .arg(environmentPrefix, slug)},
                                  {QStringLiteral("pool_pre_ping"), true}}}}}};
    const QStringList permissions{definition.permissionPrefix + QStringLiteral(".list"),
                                  definition.permissionPrefix + QStringLiteral(".read"),
                                  definition.permissionPrefix + QStringLiteral(".create"),
                                  definition.permissionPrefix + QStringLiteral(".update"),
                                  definition.permissionPrefix + QStringLiteral(".delete"),
                                  definition.permissionPrefix + QStringLiteral(".analytics"),
                                  definition.permissionPrefix + QStringLiteral(".events.publish"),
                                  definition.permissionPrefix + QStringLiteral(".events.subscribe"),
                                  QStringLiteral("system.meta.read")};
    QJsonArray permissionValues;
    for (const auto &permission : permissions) {
        permissionValues.append(permission);
    }
    const QJsonObject security{
        {QStringLiteral("$schema"), QStringLiteral("../../../schemas/fragment.schema.json")},
        {QStringLiteral("security"),
         QJsonObject{{QStringLiteral("bootstrap_enabled"), true},
                     {QStringLiteral("bootstrap_admin_key"), QStringLiteral("$env:%1_BOOTSTRAP_ADMIN_KEY").arg(environmentPrefix)},
                     {QStringLiteral("bootstrap_one_time"), true},
                     {QStringLiteral("allow_query_api_key"), false},
                     {QStringLiteral("allow_websocket_query_api_key"), false}}},
        {QStringLiteral("roles"),
         QJsonObject{{QStringLiteral("admin"), QJsonObject{{QStringLiteral("permissions"), QJsonArray{QStringLiteral("*")}}}},
                     {QStringLiteral("operator"), QJsonObject{{QStringLiteral("permissions"), permissionValues}}}}}};

    const QJsonObject columns{
        {QStringLiteral("id"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("integer")}, {QStringLiteral("primary_key"), true},
                     {QStringLiteral("nullable"), false}}},
        {QStringLiteral("name"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("string")}, {QStringLiteral("nullable"), false},
                     {QStringLiteral("max_length"), 160}, {QStringLiteral("index"), true}}},
        {QStringLiteral("status"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("string")}, {QStringLiteral("nullable"), false},
                     {QStringLiteral("default"), definition.defaultStatus}, {QStringLiteral("max_length"), 32},
                     {QStringLiteral("index"), true}}},
        {QStringLiteral("owner_id"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("string")}, {QStringLiteral("nullable"), false},
                     {QStringLiteral("max_length"), 96}, {QStringLiteral("index"), true}}},
        {QStringLiteral("amount"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("integer")}, {QStringLiteral("nullable"), false},
                     {QStringLiteral("default"), 0}, {QStringLiteral("index"), true}}},
        {QStringLiteral("metadata"), QJsonObject{{QStringLiteral("type"), QStringLiteral("json")}}},
        {QStringLiteral("created_at"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("datetime")}, {QStringLiteral("index"), true}}},
        {QStringLiteral("updated_at"), QJsonObject{{QStringLiteral("type"), QStringLiteral("datetime")}}},
        {QStringLiteral("deleted_at"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("datetime")}, {QStringLiteral("index"), true}}}};
    const QJsonObject inputProperties{
        {QStringLiteral("name"),
         QJsonObject{{QStringLiteral("type"), QStringLiteral("string")}, {QStringLiteral("minLength"), 1},
                     {QStringLiteral("maxLength"), 160}}},
        {QStringLiteral("status"), QJsonObject{{QStringLiteral("type"), QStringLiteral("string")},
                                                {QStringLiteral("minLength"), 1}, {QStringLiteral("maxLength"), 32}}},
        {QStringLiteral("owner_id"), QJsonObject{{QStringLiteral("type"), QStringLiteral("string")},
                                                  {QStringLiteral("minLength"), 1}, {QStringLiteral("maxLength"), 96}}},
        {QStringLiteral("amount"), QJsonObject{{QStringLiteral("type"), QStringLiteral("integer")},
                                                {QStringLiteral("minimum"), 0}, {QStringLiteral("maximum"), 1'000'000'000}}},
        {QStringLiteral("metadata"), QJsonObject{{QStringLiteral("type"), QStringLiteral("object")}}}};
    const QJsonObject resource{
        {QStringLiteral("$schema"), QStringLiteral("../../../schemas/fragment.schema.json")},
        {QStringLiteral("resources"),
         QJsonArray{QJsonObject{
             {QStringLiteral("database"), QStringLiteral("primary")},
             {QStringLiteral("table"), definition.table},
             {QStringLiteral("path"), definition.path},
             {QStringLiteral("auto_create"), true},
             {QStringLiteral("columns"), columns},
             {QStringLiteral("writable_fields"),
              QJsonArray{QStringLiteral("name"), QStringLiteral("status"), QStringLiteral("owner_id"),
                         QStringLiteral("amount"), QStringLiteral("metadata"), QStringLiteral("created_at"),
                         QStringLiteral("updated_at")}},
             {QStringLiteral("allowed_filters"),
              QJsonArray{QStringLiteral("status"), QStringLiteral("owner_id"), QStringLiteral("amount"),
                         QStringLiteral("created_at")}},
             {QStringLiteral("filter_operators"),
              QJsonArray{QStringLiteral("eq"), QStringLiteral("ne"), QStringLiteral("gt"), QStringLiteral("gte"),
                         QStringLiteral("lt"), QStringLiteral("lte"), QStringLiteral("in"), QStringLiteral("isnull")}},
             {QStringLiteral("search_fields"), QJsonArray{QStringLiteral("name")}},
             {QStringLiteral("allowed_sort"),
              QJsonArray{QStringLiteral("id"), QStringLiteral("name"), QStringLiteral("status"), QStringLiteral("amount"),
                         QStringLiteral("created_at")}},
             {QStringLiteral("soft_delete_field"), QStringLiteral("deleted_at")},
             {QStringLiteral("permissions"),
              QJsonObject{{QStringLiteral("list"), definition.permissionPrefix + QStringLiteral(".list")},
                          {QStringLiteral("read"), definition.permissionPrefix + QStringLiteral(".read")},
                          {QStringLiteral("create"), definition.permissionPrefix + QStringLiteral(".create")},
                          {QStringLiteral("update"), definition.permissionPrefix + QStringLiteral(".update")},
                          {QStringLiteral("delete"), definition.permissionPrefix + QStringLiteral(".delete")}}},
             {QStringLiteral("create_schema"),
              QJsonObject{{QStringLiteral("type"), QStringLiteral("object")},
                          {QStringLiteral("required"), QJsonArray{QStringLiteral("name"), QStringLiteral("owner_id")}},
                          {QStringLiteral("additionalProperties"), false},
                          {QStringLiteral("properties"), inputProperties}}},
             {QStringLiteral("update_schema"),
              QJsonObject{{QStringLiteral("type"), QStringLiteral("object")},
                          {QStringLiteral("minProperties"), 1},
                          {QStringLiteral("additionalProperties"), false},
                          {QStringLiteral("properties"), inputProperties}}},
             {QStringLiteral("cache"),
              QJsonObject{{QStringLiteral("enabled"), true}, {QStringLiteral("list_ttl_seconds"), 10},
                          {QStringLiteral("read_ttl_seconds"), 30}}}}}}};
    const QJsonObject operations{
        {QStringLiteral("$schema"), QStringLiteral("../../../schemas/fragment.schema.json")},
        {QStringLiteral("operations"),
         QJsonArray{QJsonObject{
             {QStringLiteral("name"), definition.operationName},
             {QStringLiteral("method"), QStringLiteral("GET")},
             {QStringLiteral("database"), QStringLiteral("primary")},
             {QStringLiteral("permission"), definition.permissionPrefix + QStringLiteral(".analytics")},
             {QStringLiteral("transaction"), false},
             {QStringLiteral("statements"),
              QJsonArray{QJsonObject{
                  {QStringLiteral("sql"),
                   QStringLiteral("SELECT status, COUNT(*) AS records, COALESCE(SUM(amount), 0) AS total_amount FROM %1 GROUP BY status ORDER BY status")
                       .arg(definition.table)},
                  {QStringLiteral("mode"), QStringLiteral("fetch_all")},
                  {QStringLiteral("params"), QJsonObject{}},
                  {QStringLiteral("result_name"), QStringLiteral("summary")},
                  {QStringLiteral("max_rows"), 100}}}},
             {QStringLiteral("cache"),
              QJsonObject{{QStringLiteral("enabled"), true}, {QStringLiteral("ttl_seconds"), 15},
                          {QStringLiteral("vary_by_principal"), true}}},
             {QStringLiteral("summary"), QStringLiteral("Status and amount rollup for %1").arg(definition.entity)}}}}};
    const QJsonObject events{
        {QStringLiteral("$schema"), QStringLiteral("../../../schemas/fragment.schema.json")},
        {QStringLiteral("event_channels"),
         QJsonArray{QJsonObject{{QStringLiteral("name"), slug + QStringLiteral("-updates")},
                                {QStringLiteral("path"), QStringLiteral("events/%1-updates").arg(slug)},
                                {QStringLiteral("publish_permission"), definition.permissionPrefix + QStringLiteral(".events.publish")},
                                {QStringLiteral("subscribe_permission"), definition.permissionPrefix + QStringLiteral(".events.subscribe")},
                                {QStringLiteral("websocket_enabled"), true},
                                {QStringLiteral("sse_enabled"), true},
                                {QStringLiteral("max_message_bytes"), 16384},
                                {QStringLiteral("queue_size"), 128},
                                {QStringLiteral("heartbeat_seconds"), 15}}}}};

    const QList<QPair<QString, QJsonObject>> documents{
        {QStringLiteral("app.json"), manifest},
        {QStringLiteral("config/10-databases.json"), databases},
        {QStringLiteral("config/20-security.json"), security},
        {QStringLiteral("config/40-resources.json"), resource},
        {QStringLiteral("config/50-operations.json"), operations},
        {QStringLiteral("config/60-events.json"), events},
        {QStringLiteral("graphs/domain-flow.forgegraph.json"), graphFor(definition)},
    };
    for (const auto &[path, object] : documents) {
        if (!writeJson(staging, path, object, errorMessage)) {
            cleanup();
            return false;
        }
    }
    const auto readme = QStringLiteral(
                            "# %1\n\n%2\n\n"
                            "This Editor template includes a secured CRUD resource, role permissions, aggregate RPC, cache policy, realtime "
                            "channel, and an editable operation graph.\n\n"
                            "```bash\nforge validate\nforge doctor\nforge run\n```\n\n"
                            "Set `%3_BOOTSTRAP_ADMIN_KEY` before first startup. Replace the SQLite URL with PostgreSQL through "
                            "`%3_DATABASE_URL` for production.\n")
                            .arg(definition.name, definition.description, environmentPrefix)
                            .toUtf8();
    if (!DocumentCodec::saveAtomically(staging.filePath(QStringLiteral("README.md")), readme, errorMessage)) {
        cleanup();
        return false;
    }
    if (!root.rename(stagingName, directoryName)) {
        cleanup();
        return fail(errorMessage, QStringLiteral("Could not atomically publish the staged project directory."));
    }
    return true;
}
