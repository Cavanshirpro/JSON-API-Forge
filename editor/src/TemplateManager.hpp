#pragma once

#include <QList>
#include <QString>

struct ProjectTemplate {
    QString id;
    QString name;
    QString category;
    QString description;
    QString entity;
    QString table;
    QString path;
    QString permissionPrefix;
    QString operationName;
    QString defaultStatus;
};

class TemplateManager final {
public:
    [[nodiscard]] static QList<ProjectTemplate> templates(QString *errorMessage = nullptr);
    static bool createProject(const ProjectTemplate &projectTemplate, const QString &workspaceRoot,
                              const QString &directoryName, const QString &slug, QString *errorMessage = nullptr);
};
