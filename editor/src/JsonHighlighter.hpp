#pragma once

#include <QRegularExpression>
#include <QSyntaxHighlighter>
#include <QTextCharFormat>
#include <QVector>

class JsonHighlighter final : public QSyntaxHighlighter {
    Q_OBJECT

public:
    explicit JsonHighlighter(QTextDocument *document);

protected:
    void highlightBlock(const QString &text) override;

private:
    struct Rule {
        QRegularExpression expression;
        QTextCharFormat format;
    };
    QVector<Rule> m_rules;
};
