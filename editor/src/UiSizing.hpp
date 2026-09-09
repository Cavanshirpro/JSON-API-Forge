#pragma once

#include <QGuiApplication>
#include <QScreen>
#include <QSize>
#include <QWidget>

namespace ForgeEditorUi {

inline QSize boundedSize(const QWidget *widget, const QSize &preferred, const QSize &minimum = QSize(420, 300))
{
    QScreen *screen = widget != nullptr ? QGuiApplication::screenAt(widget->frameGeometry().center()) : nullptr;
    if (screen == nullptr) {
        screen = QGuiApplication::primaryScreen();
    }
    if (screen == nullptr) {
        return preferred.expandedTo(minimum);
    }
    const QSize available = screen->availableGeometry().size();
    const QSize margin(qMin(64, available.width() / 12), qMin(64, available.height() / 12));
    const QSize maximum(qMax(minimum.width(), available.width() - margin.width()),
                        qMax(minimum.height(), available.height() - margin.height()));
    return preferred.boundedTo(maximum).expandedTo(minimum.boundedTo(maximum));
}

inline void resizeToFit(QWidget *widget, const QSize &preferred, const QSize &minimum = QSize(420, 300))
{
    if (widget != nullptr) {
        widget->resize(boundedSize(widget, preferred, minimum));
    }
}

} // namespace ForgeEditorUi
