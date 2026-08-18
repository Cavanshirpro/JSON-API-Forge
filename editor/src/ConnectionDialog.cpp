#include "ConnectionDialog.hpp"

#include "ApiClient.hpp"

#include <QCheckBox>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

ConnectionDialog::ConnectionDialog(const QUrl &lastServer, QWidget *parent)
    : QDialog(parent)
    , m_server(new QLineEdit(this))
    , m_token(new QLineEdit(this))
    , m_allowHttp(new QCheckBox(QStringLiteral("Allow plain HTTP for local development only"), this))
    , m_error(new QLabel(this))
{
    setWindowTitle(QStringLiteral("Connect to JSON API Forge"));
    setObjectName(QStringLiteral("connectionDialog"));
    setModal(true);
    resize(560, 330);
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);
    layout->setSpacing(16);
    auto *title = new QLabel(QStringLiteral("Server connection"), this);
    title->setObjectName(QStringLiteral("dialogTitle"));
    layout->addWidget(title);
    auto *description = new QLabel(
        QStringLiteral("The editor token is held in memory for this session and is never written to settings. Server policy still controls TLS, IP, project, creation and hook access."),
        this);
    description->setWordWrap(true);
    description->setObjectName(QStringLiteral("mutedText"));
    layout->addWidget(description);
    auto *form = new QFormLayout;
    form->setLabelAlignment(Qt::AlignLeft);
    m_server->setPlaceholderText(QStringLiteral("https://forge.example.com"));
    m_server->setText(lastServer.toString());
    m_server->setClearButtonEnabled(true);
    m_token->setEchoMode(QLineEdit::Password);
    m_token->setPlaceholderText(QStringLiteral("Independent EDITOR_TOKEN"));
    m_token->setClearButtonEnabled(true);
    form->addRow(QStringLiteral("Server URL"), m_server);
    form->addRow(QStringLiteral("Editor token"), m_token);
    layout->addLayout(form);
    layout->addWidget(m_allowHttp);
    m_error->setObjectName(QStringLiteral("errorText"));
    m_error->setWordWrap(true);
    m_error->hide();
    layout->addWidget(m_error);
    layout->addStretch();
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Ok, this);
    buttons->button(QDialogButtonBox::Ok)->setText(QStringLiteral("Connect"));
    buttons->button(QDialogButtonBox::Ok)->setDefault(true);
    connect(buttons, &QDialogButtonBox::accepted, this, &ConnectionDialog::validateAndAccept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    layout->addWidget(buttons);
}

QUrl ConnectionDialog::serverUrl() const
{
    return QUrl::fromUserInput(m_server->text().trimmed());
}

QByteArray ConnectionDialog::token() const
{
    return m_token->text().toUtf8();
}

bool ConnectionDialog::allowInsecureHttp() const
{
    return m_allowHttp->isChecked();
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
    const auto tokenBytes = token();
    if (tokenBytes.size() < 32 || tokenBytes.size() > 512 || tokenBytes.contains('\r') || tokenBytes.contains('\n')) {
        m_error->setText(QStringLiteral("The editor token must be 32–512 characters and contain no line breaks."));
        m_error->show();
        return;
    }
    accept();
}
