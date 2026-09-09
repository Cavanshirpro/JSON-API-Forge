#pragma once

#include <QByteArray>
#include <QList>
#include <QString>

// Bounded, single-disk ZIP reader. It never extracts paths or loads native code.
// Only stored/raw-deflate entries are supported; ZIP64 and encryption fail closed.
class SafeZipReader final {
public:
    struct FileInfo {
        QString filePath;
        qint64 size = 0;
        quint32 crc = 0;
        bool isFile = false;
        bool isDir = false;
        bool isSymLink = false;
        bool isValid() const { return !filePath.isEmpty(); }
        qsizetype dataOffset = 0;
        quint32 compressedSize = 0;
        quint16 method = 0;
    };
    enum Status { NoError, FileError };
    explicit SafeZipReader(const QString &path);
    bool exists() const { return m_error.isEmpty(); }
    bool isReadable() const { return m_error.isEmpty(); }
    Status status() const { return m_error.isEmpty() ? NoError : FileError; }
    qsizetype count() const { return m_entries.size(); }
    const QList<FileInfo> &fileInfoList() const { return m_entries; }
    QByteArray fileData(const QString &path) const;
    QString errorString() const { return m_error; }

private:
    bool parse();
    bool reject(const QString &reason) const;
    QByteArray m_bytes;
    QList<FileInfo> m_entries;
    mutable QString m_error;
};
