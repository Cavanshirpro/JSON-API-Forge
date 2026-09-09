#pragma once

#include <QPlainTextEdit>

class CodeEditor final : public QPlainTextEdit {
    Q_OBJECT

public:
    explicit CodeEditor(QWidget *parent = nullptr);
    [[nodiscard]] int lineNumberAreaWidth() const;
    void paintLineNumberArea(QPaintEvent *event);

protected:
    void resizeEvent(QResizeEvent *event) override;
    void keyPressEvent(QKeyEvent *event) override;

private slots:
    void updateLineNumberAreaWidth();
    void updateLineNumberArea(const QRect &rect, int dy);
    void highlightCurrentLine();

private:
    QWidget *m_lineNumberArea = nullptr;
};
