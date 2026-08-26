#pragma once

#include <QByteArray>
#include <QDialog>
#include <QUrl>

class QCheckBox;
class QComboBox;
class QLabel;
class QLineEdit;

class ConnectionDialog final : public QDialog {
    Q_OBJECT

public:
    enum class AuthenticationMode { SignIn, JoinInvitation, FounderSetup };

    explicit ConnectionDialog(const QUrl &lastServer, QWidget *parent = nullptr);
    [[nodiscard]] QUrl serverUrl() const;
    [[nodiscard]] AuthenticationMode authenticationMode() const;
    [[nodiscard]] QString username() const;
    [[nodiscard]] QString password() const;
    [[nodiscard]] QString displayName() const;
    [[nodiscard]] QString invitation() const;
    [[nodiscard]] QByteArray setupToken() const;
    [[nodiscard]] bool allowInsecureHttp() const;

private slots:
    void updateMode(int index);
    void validateAndAccept();

private:
    QLineEdit *m_server = nullptr;
    QComboBox *m_mode = nullptr;
    QLineEdit *m_username = nullptr;
    QLineEdit *m_password = nullptr;
    QLineEdit *m_displayName = nullptr;
    QLineEdit *m_invitation = nullptr;
    QLineEdit *m_setupToken = nullptr;
    QLabel *m_displayNameLabel = nullptr;
    QLabel *m_invitationLabel = nullptr;
    QLabel *m_setupTokenLabel = nullptr;
    QCheckBox *m_allowHttp = nullptr;
    QLabel *m_error = nullptr;
    QLabel *m_description = nullptr;
};
