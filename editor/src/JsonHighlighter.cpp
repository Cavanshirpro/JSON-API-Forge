#include "JsonHighlighter.hpp"

#include <QColor>
#include <QFont>

namespace {
QTextCharFormat makeFormat(const char *color, QFont::Weight weight = QFont::Normal)
{
    QTextCharFormat value;
    value.setForeground(QColor(QString::fromLatin1(color)));
    value.setFontWeight(weight);
    return value;
}
} // namespace

JsonHighlighter::JsonHighlighter(QTextDocument *document)
    : QSyntaxHighlighter(document)
{
    m_rules = {
        {QRegularExpression(QStringLiteral(R"("(?:\\.|[^"\\])*"(?=\s*:))")), makeFormat("#f5b94c", QFont::DemiBold)},
        {QRegularExpression(QStringLiteral(R"("(?:\\.|[^"\\])*")")), makeFormat("#8bd5ca")},
        {QRegularExpression(QStringLiteral(R"(\b-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\b)")), makeFormat("#c6a0f6")},
        {QRegularExpression(QStringLiteral(R"(\b(?:true|false|null)\b)")), makeFormat("#ed8796", QFont::DemiBold)},
        {QRegularExpression(QStringLiteral(R"([{}\[\],:])")), makeFormat("#cad3f5")},
    };
}

void JsonHighlighter::highlightBlock(const QString &text)
{
    for (const auto &rule : m_rules) {
        auto iterator = rule.expression.globalMatch(text);
        while (iterator.hasNext()) {
            const auto match = iterator.next();
            setFormat(static_cast<int>(match.capturedStart()), static_cast<int>(match.capturedLength()), rule.format);
        }
    }
}
