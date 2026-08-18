#pragma once

#include <QWidget>

class QComboBox;
class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QProcess;

struct PythonSdkSettings {
    QString mode;
    QString endpoint;
    QString clusterEndpoints;
    QString project;
    QString resource;
    QString operation;
    QString apiKeyEnvironment;
};

class PythonSdkPanel final : public QWidget {
    Q_OBJECT

public:
    explicit PythonSdkPanel(QWidget *parent = nullptr);

    [[nodiscard]] static QString generatedSnippet(const PythonSdkSettings &settings, QString *errorMessage = nullptr);

signals:
    void statusMessage(const QString &message);

private:
    [[nodiscard]] PythonSdkSettings settings() const;
    void refreshSnippet();
    void copySnippet();
    void checkPackage();
    void runHealthCheck();
    bool startPython(const QString &script, const QString &operation);

    QComboBox *m_mode = nullptr;
    QLineEdit *m_endpoint = nullptr;
    QLineEdit *m_clusterEndpoints = nullptr;
    QLineEdit *m_project = nullptr;
    QLineEdit *m_resource = nullptr;
    QLineEdit *m_operation = nullptr;
    QLineEdit *m_apiKeyEnvironment = nullptr;
    QLabel *m_install = nullptr;
    QLabel *m_result = nullptr;
    QPlainTextEdit *m_snippet = nullptr;
    QProcess *m_process = nullptr;
    QString m_processOperation;
};
