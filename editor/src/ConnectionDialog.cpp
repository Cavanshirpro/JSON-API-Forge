#include "ConnectionDialog.hpp"

#include "UiSizing.hpp"

#include "ApiClient.hpp"

#include <QCheckBox>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPixmap>
#include <QPushButton>
#include <QRegularExpression>
#include <QVBoxLayout>

#include <algorithm>

ConnectionDialog::ConnectionDialog(const QUrl &lastServer, QWidget *parent)
    : QDialog(parent)
    , m_server(new QLineEdit(this))
    , m_mode(new QComboBox(this))
    , m_username(new QLineEdit(this))
    , m_password(new QLineEdit(this))
    , m_displayName(new QLineEdit(this))
    , m_invitation(new QLineEdit(this))
    , m_setupToken(new QLineEdit(this))
    , m_allowHttp(new QCheckBox(QStringLiteral("Allow plain HTTP for loopback development only"), this))
    , m_error(new QLabel(this))
    , m_description(new QLabel(this))
{
    setWindowTitle(QStringLiteral("Connect to JSON API Forge"));
    setObjectName(QStringLiteral("connectionDialog"));
    setModal(true);
    ForgeEditorUi::resizeToFit(this, QSize(620, 520));
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);
    layout->setSpacing(14);
    auto *brand = new QLabel(this);
    brand->setPixmap(QPixmap(QStringLiteral(":/branding/mark.png"))
                         .scaled(68, 68, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    brand->setAlignment(Qt::AlignCenter);
    layout->addWidget(brand);
    auto *title = new QLabel(QStringLiteral("Secure server workspace"), this);
    title->setObjectName(QStringLiteral("dialogTitle"));
    title->setAlignment(Qt::AlignCenter);
    layout->addWidget(title);
    m_description->setWordWrap(true);
    m_description->setObjectName(QStringLiteral("mutedText"));
    m_description->setAlignment(Qt::AlignCenter);
    layout->addWidget(m_description);

    auto *form = new QFormLayout;
    form->setLabelAlignment(Qt::AlignLeft);
    form->setVerticalSpacing(10);
    m_server->setPlaceholderText(QStringLiteral("https://forge.example.com"));
    m_server->setText(lastServer.toString());
    m_server->setClearButtonEnabled(true);
    m_mode->addItem(QStringLiteral("Sign in with worker account"),
                    static_cast<int>(AuthenticationMode::SignIn));
    m_mode->addItem(QStringLiteral("Join with an invitation"),
                    static_cast<int>(AuthenticationMode::JoinInvitation));
    m_mode->addItem(QStringLiteral("Create the founder (one time)"),
                    static_cast<int>(AuthenticationMode::FounderSetup));
    m_username->setPlaceholderText(QStringLiteral("worker.name"));
    m_username->setClearButtonEnabled(true);
    m_password->setEchoMode(QLineEdit::Password);
    m_password->setPlaceholderText(QStringLiteral("Account password"));
    m_password->setClearButtonEnabled(true);
    m_displayName->setPlaceholderText(QStringLiteral("Display name"));
    m_displayName->setClearButtonEnabled(true);
    m_invitation->setEchoMode(QLineEdit::Password);
    m_invitation->setPlaceholderText(QStringLiteral("Single-use invitation token"));
    m_invitation->setClearButtonEnabled(true);
    m_setupToken->setEchoMode(QLineEdit::Password);
    m_setupToken->setPlaceholderText(QStringLiteral("One-time EDITOR_TOKEN"));
    m_setupToken->setClearButtonEnabled(true);
    form->addRow(QStringLiteral("Server URL"), m_server);
    form->addRow(QStringLiteral("Access flow"), m_mode);
    form->addRow(QStringLiteral("Username"), m_username);
    form->addRow(QStringLiteral("Password"), m_password);
    m_displayNameLabel = new QLabel(QStringLiteral("Display name"), this);
    form->addRow(m_displayNameLabel, m_displayName);
    m_invitationLabel = new QLabel(QStringLiteral("Invitation"), this);
    form->addRow(m_invitationLabel, m_invitation);
    m_setupTokenLabel = new QLabel(QStringLiteral("Setup token"), this);
    form->addRow(m_setupTokenLabel, m_setupToken);
    layout->addLayout(form);
    layout->addWidget(m_allowHttp);
    m_error->setObjectName(QStringLiteral("errorText"));
    m_error->setWordWrap(true);
    m_error->hide();
    layout->addWidget(m_error);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Ok, this);
    buttons->button(QDialogButtonBox::Ok)->setText(QStringLiteral("Continue securely"));
    buttons->button(QDialogButtonBox::Ok)->setDefault(true);
    connect(buttons, &QDialogButtonBox::accepted, this, &ConnectionDialog::validateAndAccept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(m_mode, &QComboBox::currentIndexChanged, this, &ConnectionDialog::updateMode);
    layout->addWidget(buttons);
    updateMode(0);
}

QUrl ConnectionDialog::serverUrl() const
{
    return QUrl::fromUserInput(m_server->text().trimmed());
}

ConnectionDialog::AuthenticationMode ConnectionDialog::authenticationMode() const
{
    return static_cast<AuthenticationMode>(m_mode->currentData().toInt());
}

QString ConnectionDialog::username() const
{
    return m_username->text().trimmed();
}

QString ConnectionDialog::password() const
{
    return m_password->text();
}

QString ConnectionDialog::displayName() const
{
    return m_displayName->text().trimmed();
}

QString ConnectionDialog::invitation() const
{
    return m_invitation->text().trimmed();
}

QByteArray ConnectionDialog::setupToken() const
{
    return m_setupToken->text().toUtf8();
}

bool ConnectionDialog::allowInsecureHttp() const
{
    return m_allowHttp->isChecked();
}

void ConnectionDialog::updateMode(int)
{
    const auto mode = authenticationMode();
    const bool enrollment = mode != AuthenticationMode::SignIn;
    const bool invitation = mode == AuthenticationMode::JoinInvitation;
    const bool setup = mode == AuthenticationMode::FounderSetup;
    m_displayName->setVisible(enrollment);
    m_displayNameLabel->setVisible(enrollment);
    m_invitation->setVisible(invitation);
    m_invitationLabel->setVisible(invitation);
    m_setupToken->setVisible(setup);
    m_setupTokenLabel->setVisible(setup);
    if (mode == AuthenticationMode::SignIn) {
        m_description->setText(QStringLiteral(
            "Passwords and bearer sessions remain in memory. The Editor never stores them or follows redirects."));
    } else if (mode == AuthenticationMode::JoinInvitation) {
        m_description->setText(QStringLiteral(
            "Use the founder-issued, single-use invitation to create your own account and scoped memberships."));
    } else {
        m_description->setText(QStringLiteral(
            "First deployment only. After setup, disable EDITOR_SETUP_ENABLED and remove EDITOR_TOKEN."));
    }
}

void ConnectionDialog::validateAndAccept()
{
    QUrl normalized;
    QString error;
    if (!ApiClient::normalizeServerUrl(serverUrl(), allowInsecureHttp(), &normalized, &error)) {
        m_error->setText(error);
        m_error->show();
        return;
    }
    static const QRegularExpression UsernamePattern(
        QStringLiteral(R"(^[A-Za-z0-9](?:[A-Za-z0-9._-]{1,30}[A-Za-z0-9])$)"));
    if (!UsernamePattern.match(username()).hasMatch()) {
        m_error->setText(QStringLiteral("Username must contain 3–32 safe letters, digits, dots, dashes or underscores."));
        m_error->show();
        return;
    }
    if (password().size() < 12 || password().size() > 256) {
        m_error->setText(QStringLiteral("Password must contain 12–256 characters."));
        m_error->show();
        return;
    }
    const auto mode = authenticationMode();
    if (mode != AuthenticationMode::SignIn && (displayName().isEmpty() || displayName().size() > 80)) {
        m_error->setText(QStringLiteral("Display name must contain 1–80 characters."));
        m_error->show();
        return;
    }
    static const QRegularExpression InvitationPattern(
        QStringLiteral(R"(\Ajfi_[A-Za-z0-9_-]{40,80}\z)"));
    if (mode == AuthenticationMode::JoinInvitation
        && !InvitationPattern.match(invitation()).hasMatch()) {
        m_error->setText(QStringLiteral("Enter the complete single-use invitation token."));
        m_error->show();
        return;
    }
    const auto token = setupToken();
    const bool setupTokenInvalid = token.size() < 32 || token.size() > 512
        || std::any_of(token.cbegin(), token.cend(), [](char character) {
               const auto byte = static_cast<unsigned char>(character);
               return byte < 0x21U || byte > 0x7eU;
           });
    if (mode == AuthenticationMode::FounderSetup && setupTokenInvalid) {
        m_error->setText(QStringLiteral("Setup token must contain 32–512 printable ASCII characters without spaces."));
        m_error->show();
        return;
    }
    accept();
}
