#pragma once

#include <QDialog>
#include <QStringList>

class QCheckBox;
class QDoubleSpinBox;
class QListWidget;
class QSpinBox;

struct EditorPreferences final {
    int requestTimeoutMs = 60'000;
    int authenticationTimeoutMs = 120'000;
    int uploadTimeoutMs = 300'000;
    int downloadTimeoutMs = 300'000;
    int safeGetRetries = 1;
    int retryBaseDelayMs = 750;
    int maxResponseMiB = 8;
    bool confirmDiscard = true;
    bool restoreWindowLayout = true;
    bool rightDragPan = true;
    double graphZoomSensitivity = 1.0;
    QStringList serverHistory;

    [[nodiscard]] static EditorPreferences load();
    void save() const;
    void clamp();
};

class EditorSettingsDialog final : public QDialog {
    Q_OBJECT

public:
    explicit EditorSettingsDialog(const EditorPreferences &preferences, QWidget *parent = nullptr);
    [[nodiscard]] EditorPreferences preferences() const;

private:
    QSpinBox *m_requestTimeout = nullptr;
    QSpinBox *m_authenticationTimeout = nullptr;
    QSpinBox *m_uploadTimeout = nullptr;
    QSpinBox *m_downloadTimeout = nullptr;
    QSpinBox *m_safeGetRetries = nullptr;
    QSpinBox *m_retryDelay = nullptr;
    QSpinBox *m_maxResponse = nullptr;
    QCheckBox *m_confirmDiscard = nullptr;
    QCheckBox *m_restoreLayout = nullptr;
    QCheckBox *m_rightDragPan = nullptr;
    QDoubleSpinBox *m_zoomSensitivity = nullptr;
    QListWidget *m_serverHistory = nullptr;
};
