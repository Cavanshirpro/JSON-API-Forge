#include "EditorSettings.hpp"

#include <cmath>

#include "UiSizing.hpp"

#include <QCheckBox>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QSettings>
#include <QSpinBox>
#include <QTabWidget>
#include <QUrl>
#include <QVBoxLayout>

#include <utility>

namespace {
constexpr int MinimumTimeoutMs = 1'000;
constexpr int MaximumTimeoutMs = 900'000;

QSpinBox *timeoutBox(int value, QWidget *parent)
{
    auto *box = new QSpinBox(parent);
    box->setRange(MinimumTimeoutMs / 1000, MaximumTimeoutMs / 1000);
    box->setSuffix(QStringLiteral(" s"));
    box->setValue(value / 1000);
    return box;
}
} // namespace

void EditorPreferences::clamp()
{
    requestTimeoutMs = qBound(MinimumTimeoutMs, requestTimeoutMs, MaximumTimeoutMs);
    authenticationTimeoutMs = qBound(MinimumTimeoutMs, authenticationTimeoutMs, MaximumTimeoutMs);
    uploadTimeoutMs = qBound(MinimumTimeoutMs, uploadTimeoutMs, MaximumTimeoutMs);
    downloadTimeoutMs = qBound(MinimumTimeoutMs, downloadTimeoutMs, MaximumTimeoutMs);
    safeGetRetries = qBound(0, safeGetRetries, 3);
    retryBaseDelayMs = qBound(100, retryBaseDelayMs, 10'000);
    maxResponseMiB = qBound(1, maxResponseMiB, 64);
    graphZoomSensitivity = std::isfinite(graphZoomSensitivity) ? qBound(0.25, graphZoomSensitivity, 3.0) : 1.0;
    QStringList sanitizedHistory;
    for (const auto &entry : std::as_const(serverHistory)) {
        const QUrl url(entry);
        if (entry.size() > 2048 || !url.isValid() || url.host().isEmpty()
            || !url.userInfo().isEmpty() || url.hasQuery() || url.hasFragment()
            || (url.scheme() != QStringLiteral("https") && url.scheme() != QStringLiteral("http"))) {
            continue;
        }
        const auto normalized = url.toString();
        if (!sanitizedHistory.contains(normalized)) {
            sanitizedHistory.append(normalized);
        }
        if (sanitizedHistory.size() == 10) {
            break;
        }
    }
    serverHistory = sanitizedHistory;
}

EditorPreferences EditorPreferences::load()
{
    QSettings settings;
    EditorPreferences value;
    value.requestTimeoutMs = settings.value(QStringLiteral("network/requestTimeoutMs"), value.requestTimeoutMs).toInt();
    value.authenticationTimeoutMs = settings.value(QStringLiteral("network/authenticationTimeoutMs"), value.authenticationTimeoutMs).toInt();
    const int legacyTransferTimeout = settings.value(QStringLiteral("network/transferTimeoutMs"),
                                                      value.uploadTimeoutMs).toInt();
    value.uploadTimeoutMs = settings.value(QStringLiteral("network/uploadTimeoutMs"),
                                            legacyTransferTimeout).toInt();
    value.downloadTimeoutMs = settings.value(QStringLiteral("network/downloadTimeoutMs"),
                                              legacyTransferTimeout).toInt();
    value.safeGetRetries = settings.value(QStringLiteral("network/safeGetRetries"), value.safeGetRetries).toInt();
    value.retryBaseDelayMs = settings.value(QStringLiteral("network/retryBaseDelayMs"), value.retryBaseDelayMs).toInt();
    value.maxResponseMiB = settings.value(QStringLiteral("network/maxResponseMiB"), value.maxResponseMiB).toInt();
    value.confirmDiscard = settings.value(QStringLiteral("editor/confirmDiscard"), value.confirmDiscard).toBool();
    value.restoreWindowLayout = settings.value(QStringLiteral("editor/restoreWindowLayout"), value.restoreWindowLayout).toBool();
    value.rightDragPan = settings.value(QStringLiteral("editor/rightDragPan"), value.rightDragPan).toBool();
    value.graphZoomSensitivity = settings.value(QStringLiteral("editor/graphZoomSensitivity"), value.graphZoomSensitivity).toDouble();
    value.serverHistory = settings.value(QStringLiteral("connection/serverHistory")).toStringList();
    value.clamp();
    return value;
}

void EditorPreferences::save() const
{
    auto value = *this;
    value.clamp();
    QSettings settings;
    settings.setValue(QStringLiteral("network/requestTimeoutMs"), value.requestTimeoutMs);
    settings.setValue(QStringLiteral("network/authenticationTimeoutMs"), value.authenticationTimeoutMs);
    settings.setValue(QStringLiteral("network/uploadTimeoutMs"), value.uploadTimeoutMs);
    settings.setValue(QStringLiteral("network/downloadTimeoutMs"), value.downloadTimeoutMs);
    settings.remove(QStringLiteral("network/transferTimeoutMs"));
    settings.setValue(QStringLiteral("network/safeGetRetries"), value.safeGetRetries);
    settings.setValue(QStringLiteral("network/retryBaseDelayMs"), value.retryBaseDelayMs);
    settings.setValue(QStringLiteral("network/maxResponseMiB"), value.maxResponseMiB);
    settings.setValue(QStringLiteral("editor/confirmDiscard"), value.confirmDiscard);
    settings.setValue(QStringLiteral("editor/restoreWindowLayout"), value.restoreWindowLayout);
    settings.setValue(QStringLiteral("editor/rightDragPan"), value.rightDragPan);
    settings.setValue(QStringLiteral("editor/graphZoomSensitivity"), value.graphZoomSensitivity);
    settings.setValue(QStringLiteral("connection/serverHistory"), value.serverHistory);
}

EditorSettingsDialog::EditorSettingsDialog(const EditorPreferences &preferences, QWidget *parent)
    : QDialog(parent)
{
    setWindowTitle(QStringLiteral("Editor settings"));
    setModal(true);
    ForgeEditorUi::resizeToFit(this, QSize(660, 520));
    auto *root = new QVBoxLayout(this);
    auto *tabs = new QTabWidget(this);

    auto *networkPage = new QWidget(tabs);
    auto *networkLayout = new QVBoxLayout(networkPage);
    auto *networkHelp = new QLabel(
        QStringLiteral("Timeouts are per request. Only safe GET requests may be retried; saves, setup and other mutations are never replayed automatically."),
        networkPage);
    networkHelp->setWordWrap(true);
    networkHelp->setObjectName(QStringLiteral("policyCard"));
    networkLayout->addWidget(networkHelp);
    auto *networkForm = new QFormLayout;
    m_requestTimeout = timeoutBox(preferences.requestTimeoutMs, networkPage);
    m_authenticationTimeout = timeoutBox(preferences.authenticationTimeoutMs, networkPage);
    m_uploadTimeout = timeoutBox(preferences.uploadTimeoutMs, networkPage);
    m_downloadTimeout = timeoutBox(preferences.downloadTimeoutMs, networkPage);
    m_safeGetRetries = new QSpinBox(networkPage);
    m_safeGetRetries->setRange(0, 3);
    m_safeGetRetries->setValue(preferences.safeGetRetries);
    m_retryDelay = new QSpinBox(networkPage);
    m_retryDelay->setRange(100, 10'000);
    m_retryDelay->setSingleStep(100);
    m_retryDelay->setSuffix(QStringLiteral(" ms"));
    m_retryDelay->setValue(preferences.retryBaseDelayMs);
    m_maxResponse = new QSpinBox(networkPage);
    m_maxResponse->setRange(1, 64);
    m_maxResponse->setSuffix(QStringLiteral(" MiB"));
    m_maxResponse->setValue(preferences.maxResponseMiB);
    networkForm->addRow(QStringLiteral("Normal request timeout"), m_requestTimeout);
    networkForm->addRow(QStringLiteral("Sign-in/setup timeout"), m_authenticationTimeout);
    networkForm->addRow(QStringLiteral("Upload timeout"), m_uploadTimeout);
    networkForm->addRow(QStringLiteral("Download timeout"), m_downloadTimeout);
    networkForm->addRow(QStringLiteral("Safe GET retry count"), m_safeGetRetries);
    networkForm->addRow(QStringLiteral("Retry base delay"), m_retryDelay);
    networkForm->addRow(QStringLiteral("Maximum JSON response"), m_maxResponse);
    networkLayout->addLayout(networkForm);
    auto *historyLabel = new QLabel(QStringLiteral("Saved server history"), networkPage);
    networkLayout->addWidget(historyLabel);
    m_serverHistory = new QListWidget(networkPage);
    m_serverHistory->addItems(preferences.serverHistory);
    m_serverHistory->setMaximumHeight(100);
    networkLayout->addWidget(m_serverHistory);
    auto *historyButtons = new QHBoxLayout;
    auto *removeSelected = new QPushButton(QStringLiteral("Remove selected"), networkPage);
    auto *clearHistory = new QPushButton(QStringLiteral("Clear history"), networkPage);
    historyButtons->addWidget(removeSelected);
    historyButtons->addWidget(clearHistory);
    historyButtons->addStretch();
    networkLayout->addLayout(historyButtons);
    connect(removeSelected, &QPushButton::clicked, this, [this] {
        delete m_serverHistory->takeItem(m_serverHistory->currentRow());
    });
    connect(clearHistory, &QPushButton::clicked, m_serverHistory, &QListWidget::clear);
    networkLayout->addStretch();
    tabs->addTab(networkPage, QStringLiteral("Network"));

    auto *editorPage = new QWidget(tabs);
    auto *editorLayout = new QVBoxLayout(editorPage);
    m_confirmDiscard = new QCheckBox(QStringLiteral("Confirm before discarding unsaved edits"), editorPage);
    m_confirmDiscard->setChecked(preferences.confirmDiscard);
    m_restoreLayout = new QCheckBox(QStringLiteral("Restore the previous window and dock layout"), editorPage);
    m_restoreLayout->setChecked(preferences.restoreWindowLayout);
    m_rightDragPan = new QCheckBox(QStringLiteral("Pan the graph canvas with right-button drag"), editorPage);
    m_rightDragPan->setChecked(preferences.rightDragPan);
    m_zoomSensitivity = new QDoubleSpinBox(editorPage);
    m_zoomSensitivity->setRange(0.25, 3.0);
    m_zoomSensitivity->setSingleStep(0.1);
    m_zoomSensitivity->setDecimals(2);
    m_zoomSensitivity->setValue(preferences.graphZoomSensitivity);
    editorLayout->addWidget(m_confirmDiscard);
    editorLayout->addWidget(m_restoreLayout);
    editorLayout->addWidget(m_rightDragPan);
    auto *editorForm = new QFormLayout;
    editorForm->addRow(QStringLiteral("Graph zoom sensitivity"), m_zoomSensitivity);
    editorLayout->addLayout(editorForm);
    editorLayout->addStretch();
    tabs->addTab(editorPage, QStringLiteral("Editor / Advanced"));

    root->addWidget(tabs, 1);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Save, this);
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    root->addWidget(buttons);
}

EditorPreferences EditorSettingsDialog::preferences() const
{
    EditorPreferences value;
    value.requestTimeoutMs = m_requestTimeout->value() * 1000;
    value.authenticationTimeoutMs = m_authenticationTimeout->value() * 1000;
    value.uploadTimeoutMs = m_uploadTimeout->value() * 1000;
    value.downloadTimeoutMs = m_downloadTimeout->value() * 1000;
    value.safeGetRetries = m_safeGetRetries->value();
    value.retryBaseDelayMs = m_retryDelay->value();
    value.maxResponseMiB = m_maxResponse->value();
    value.confirmDiscard = m_confirmDiscard->isChecked();
    value.restoreWindowLayout = m_restoreLayout->isChecked();
    value.rightDragPan = m_rightDragPan->isChecked();
    value.graphZoomSensitivity = m_zoomSensitivity->value();
    for (int row = 0; row < m_serverHistory->count(); ++row) {
        value.serverHistory.append(m_serverHistory->item(row)->text());
    }
    value.clamp();
    return value;
}
