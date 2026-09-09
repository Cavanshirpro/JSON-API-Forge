#pragma once

#include <QByteArray>
#include <QFile>
#include <QList>
#include <QString>

// Test-only ZIP producer built on Qt's public zlib encoder. The production
// reader uses a different decoder and is also tested with Python zipfile data.
class ZipFixtureWriter final {
public:
    enum Status { NoError, FileError };
    enum CompressionPolicy { AlwaysCompress };
    explicit ZipFixtureWriter(QString path) : m_path(std::move(path)) {}
    void setCompressionPolicy(CompressionPolicy) {}
    void addFile(const QString &name, const QByteArray &bytes) { add(name, bytes, 0100644U); }
    void addDirectory(const QString &name) { add(name + u'/', {}, 0040755U); }
    void addSymLink(const QString &name, const QString &target) { add(name, target.toUtf8(), 0120777U); }
    Status status() const { return m_status; }
    void close()
    {
        const auto start = static_cast<quint32>(m_output.size());
        for (const auto &entry : m_directory) {
            m_output.append(entry);
        }
        const auto size = static_cast<quint32>(m_output.size()) - start;
        put32(m_output, 0x06054b50U);
        put16(m_output, 0); put16(m_output, 0);
        put16(m_output, static_cast<quint16>(m_directory.size()));
        put16(m_output, static_cast<quint16>(m_directory.size()));
        put32(m_output, size); put32(m_output, start); put16(m_output, 0);
        QFile file(m_path);
        if (!file.open(QIODevice::WriteOnly) || file.write(m_output) != m_output.size()) {
            m_status = FileError;
        }
    }
private:
    static void put16(QByteArray &out, quint16 value)
    {
        out.append(static_cast<char>(value & 255U));
        out.append(static_cast<char>(value >> 8U));
    }
    static void put32(QByteArray &out, quint32 value)
    {
        put16(out, static_cast<quint16>(value & 65535U));
        put16(out, static_cast<quint16>(value >> 16U));
    }
    void add(const QString &name, const QByteArray &bytes, quint32 mode)
    {
        const auto filename = name.toUtf8();
        quint32 crc = 0xffffffffU;
        for (const auto byte : bytes) {
            crc ^= static_cast<quint8>(byte);
            for (int bit = 0; bit < 8; ++bit) {
                crc = (crc >> 1U) ^ (0xedb88320U & (0U - (crc & 1U)));
            }
        }
        crc = ~crc;
        const auto compressed = bytes.isEmpty() ? QByteArray{} : qCompress(bytes, 9);
        const auto raw = compressed.isEmpty() ? QByteArray{} : compressed.mid(6, compressed.size() - 10);
        const auto method = static_cast<quint16>(bytes.isEmpty() ? 0 : 8);
        const auto offset = static_cast<quint32>(m_output.size());
        QByteArray common;
        put16(common, 20); put16(common, 0x0800); put16(common, method);
        put16(common, 0); put16(common, 0);
        put32(common, crc); put32(common, static_cast<quint32>(raw.size()));
        put32(common, static_cast<quint32>(bytes.size()));
        put16(common, static_cast<quint16>(filename.size())); put16(common, 0);
        put32(m_output, 0x04034b50U);
        m_output += common + filename + raw;
        QByteArray central;
        put32(central, 0x02014b50U); put16(central, 0x0314);
        central += common;
        put16(central, 0); put16(central, 0); put16(central, 0);
        put32(central, mode << 16U); put32(central, offset);
        central += filename;
        m_directory.append(central);
    }
    QString m_path;
    QByteArray m_output;
    QList<QByteArray> m_directory;
    Status m_status = NoError;
};
