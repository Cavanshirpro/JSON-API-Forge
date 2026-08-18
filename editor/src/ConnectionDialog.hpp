#pragma once

#include <QByteArray>
#include <QDialog>
#include <QUrl>

class QCheckBox;
class QLabel;
class QLineEdit;

class ConnectionDialog final : public QDialog {
    Q_OBJECT

public:
    explicit ConnectionDialog(const QUrl &lastServer, QWidget *parent = nullptr);
    [[nodiscard]] QUrl serverUrl() const;
    [[nodiscard]] QByteArray token() const;
    [[nodiscard]] bool allowInsecureHttp() const;

private slots:
    void validateAndAccept();

private:
    QLineEdit *m_server = nullptr;
    QLineEdit *m_token = nullptr;
    QCheckBox *m_allowHttp = nullptr;
    QLabel *m_error = nullptr;
};
