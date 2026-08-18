#include "MainWindow.hpp"

#include <QApplication>
#include <QCommandLineOption>
#include <QCommandLineParser>
#include <QIcon>
#include <QPropertyAnimation>
#include <QStyleFactory>
#include <QTimer>

int main(int argc, char *argv[])
{
    QApplication application(argc, argv);
    application.setApplicationDisplayName(QStringLiteral("JSON API Forge Editor"));
    application.setApplicationVersion(QStringLiteral("0.4.2"));
    application.setWindowIcon(QIcon(QStringLiteral(":/branding/logo.png")));
    application.setStyle(QStyleFactory::create(QStringLiteral("Fusion")));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Policy-aware visual and code editor for JSON API Forge"));
    parser.addHelpOption();
    parser.addVersionOption();
    const QCommandLineOption screenshotOption(
        QStringList{QStringLiteral("screenshot")},
        QStringLiteral("Render the initial window to <path> and exit (visual regression/packaging smoke test)."),
        QStringLiteral("path"));
    parser.addOption(screenshotOption);
    parser.process(application);

    MainWindow window;
    const auto screenshotPath = parser.value(screenshotOption);
    const bool renderingPreview = !screenshotPath.isEmpty();
    window.setWindowOpacity(renderingPreview ? 1.0 : 0.0);
    window.show();
    if (renderingPreview) {
        QTimer::singleShot(500, &window, [&application, &window, screenshotPath] {
            application.exit(window.grab().save(screenshotPath, "PNG") ? 0 : 2);
        });
    } else {
        auto *startup = new QPropertyAnimation(&window, "windowOpacity", &window);
        startup->setDuration(320);
        startup->setStartValue(0.0);
        startup->setEndValue(1.0);
        startup->setEasingCurve(QEasingCurve::OutCubic);
        startup->start(QAbstractAnimation::DeleteWhenStopped);
    }
    return QApplication::exec();
}
