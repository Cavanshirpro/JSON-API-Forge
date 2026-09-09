#include "SafeZipReader.hpp"

#include <QFile>
#include <QtEndian>

#include <algorithm>
#include <limits>

extern "C" {
#include "puff.h"
}

namespace {
constexpr qsizetype MaxArchive = 64 * 1024 * 1024;
constexpr quint64 MaxEntry = 64 * 1024 * 1024;
constexpr quint64 MaxTotal = 128 * 1024 * 1024;

quint16 u16(const QByteArray &data, qsizetype offset)
{
    return qFromLittleEndian<quint16>(data.constData() + offset);
}

quint32 u32(const QByteArray &data, qsizetype offset)
{
    return qFromLittleEndian<quint32>(data.constData() + offset);
}

bool safeExtra(const QByteArray &data, qsizetype offset, qsizetype length)
{
    const auto end = offset + length;
    while (offset < end) {
        if (end - offset < 4) {
            return false;
        }
        const auto tag = u16(data, offset);
        const auto size = u16(data, offset + 2);
        offset += 4;
        // ZIP64, PKWARE Unix links and alternate Unicode paths are deliberately
        // unsupported. Never let a second path/size representation change policy.
        if (tag == 0x0001 || tag == 0x000d || tag == 0x7075 || size > end - offset) {
            return false;
        }
        offset += size;
    }
    return offset == end;
}
} // namespace

SafeZipReader::SafeZipReader(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() < 22 || file.size() > MaxArchive) {
        reject(QStringLiteral("The ZIP must be a readable archive no larger than 64 MiB."));
        return;
    }
    // Parse and decompress the same bounded snapshot, even if the source file
    // is renamed, replaced or appended to during import.
    m_bytes = file.read(MaxArchive + 1);
    if (file.error() != QFile::NoError || m_bytes.size() > MaxArchive
        || m_bytes.size() != file.size() || !parse()) {
        if (m_error.isEmpty()) {
            reject(QStringLiteral("The ZIP is truncated or changed while being read."));
        }
        m_entries.clear();
    }
}

bool SafeZipReader::reject(const QString &reason) const
{
    m_error = reason;
    return false;
}

bool SafeZipReader::parse()
{
    if (m_bytes.size() < 22) {
        return reject(QStringLiteral("The ZIP end record is missing."));
    }
    qsizetype end = -1;
    const auto lower = qMax<qsizetype>(0, m_bytes.size() - 22 - 65535);
    for (auto at = m_bytes.size() - 22; at >= lower; --at) {
        if (u32(m_bytes, at) == 0x06054b50U && at + 22 + u16(m_bytes, at + 20) == m_bytes.size()) {
            end = at;
            break;
        }
    }
    if (end < 0 || u16(m_bytes, end + 4) != 0 || u16(m_bytes, end + 6) != 0) {
        return reject(QStringLiteral("The ZIP end record is invalid or uses multiple disks."));
    }
    const auto count = u16(m_bytes, end + 10);
    const quint64 directorySize = u32(m_bytes, end + 12);
    const quint64 directoryOffset = u32(m_bytes, end + 16);
    if (count == 0 || count > 256 || u16(m_bytes, end + 8) != count
        || directoryOffset + directorySize != static_cast<quint64>(end)) {
        return reject(QStringLiteral("The ZIP is empty, has too many entries, or has an invalid directory."));
    }
    auto at = static_cast<qsizetype>(directoryOffset);
    quint64 total = 0;
    QList<QPair<qsizetype, qsizetype>> ranges;
    for (quint16 index = 0; index < count; ++index) {
        if (end - at < 46 || u32(m_bytes, at) != 0x02014b50U) {
            return reject(QStringLiteral("The ZIP directory entry is truncated or malformed."));
        }
        const auto flags = u16(m_bytes, at + 8);
        const auto method = u16(m_bytes, at + 10);
        const auto crc = u32(m_bytes, at + 16);
        const quint64 compressed = u32(m_bytes, at + 20);
        const quint64 size = u32(m_bytes, at + 24);
        const auto nameLength = u16(m_bytes, at + 28);
        const auto extraLength = u16(m_bytes, at + 30);
        const auto commentLength = u16(m_bytes, at + 32);
        const auto attrs = u32(m_bytes, at + 38);
        const quint64 local = u32(m_bytes, at + 42);
        const auto headerSize = qsizetype(46) + nameLength + extraLength + commentLength;
        if (headerSize > end - at || nameLength == 0 || nameLength > 512
            || u16(m_bytes, at + 6) > 20 || u16(m_bytes, at + 34) != 0
            || (flags & ~quint16(0x080e)) != 0 || (method != 0 && method != 8)
            || (method == 0 && ((flags & 6U) != 0 || compressed != size))) {
            return reject(QStringLiteral("The ZIP uses malformed, encrypted or unsupported entry metadata."));
        }
        if (size > MaxEntry || compressed > static_cast<quint64>(MaxArchive)
            || size > MaxTotal - total) {
            return reject(QStringLiteral("The ZIP exceeds the per-file or 128 MiB extracted-size limit."));
        }
        if (size > compressed * 100U + 1024U * 1024U) {
            return reject(QStringLiteral("The ZIP compression ratio exceeds the safe import limit."));
        }
        total += size;
        const auto rawName = m_bytes.mid(at + 46, nameLength);
        const auto name = QString::fromUtf8(rawName);
        if (rawName.contains('\0') || name.toUtf8() != rawName
            || !safeExtra(m_bytes, at + 46 + nameLength, extraLength)
            || local + 30 > directoryOffset) {
            return reject(QStringLiteral("The ZIP contains invalid names, link/ZIP64 metadata or offsets."));
        }
        const auto loc = static_cast<qsizetype>(local);
        const auto localNameLength = u16(m_bytes, loc + 26);
        const auto localExtraLength = u16(m_bytes, loc + 28);
        const quint64 dataOffset = local + 30 + localNameLength + localExtraLength;
        if (dataOffset > directoryOffset || compressed > directoryOffset - dataOffset
            || u32(m_bytes, loc) != 0x04034b50U || u16(m_bytes, loc + 4) != u16(m_bytes, at + 6)
            || u16(m_bytes, loc + 6) != flags || u16(m_bytes, loc + 8) != method
            || m_bytes.mid(loc + 30, localNameLength) != rawName
            || !safeExtra(m_bytes, loc + 30 + localNameLength, localExtraLength)) {
            return reject(QStringLiteral("The ZIP local header disagrees with its directory."));
        }
        quint64 dataEnd = dataOffset + compressed;
        if ((flags & 8U) == 0) {
            if (u32(m_bytes, loc + 14) != crc || u32(m_bytes, loc + 18) != compressed
                || u32(m_bytes, loc + 22) != size) {
                return reject(QStringLiteral("The ZIP local size/CRC metadata is inconsistent."));
            }
        } else {
            // Streamed archives use a data descriptor instead of local sizes.
            if ((u32(m_bytes, loc + 14) != 0 && u32(m_bytes, loc + 14) != crc)
                || (u32(m_bytes, loc + 18) != 0 && u32(m_bytes, loc + 18) != compressed)
                || (u32(m_bytes, loc + 22) != 0 && u32(m_bytes, loc + 22) != size)) {
                return reject(QStringLiteral("The ZIP streamed local size/CRC metadata is inconsistent."));
            }
            auto descriptor = static_cast<qsizetype>(dataEnd);
            if (directoryOffset - dataEnd >= 4 && u32(m_bytes, descriptor) == 0x08074b50U) {
                descriptor += 4;
            }
            if (static_cast<quint64>(descriptor) + 12 > directoryOffset
                || u32(m_bytes, descriptor) != crc || u32(m_bytes, descriptor + 4) != compressed
                || u32(m_bytes, descriptor + 8) != size) {
                return reject(QStringLiteral("The ZIP data descriptor is invalid."));
            }
            dataEnd = static_cast<quint64>(descriptor) + 12;
        }
        const auto host = static_cast<quint16>(u16(m_bytes, at + 4) >> 8U);
        const auto kind = (attrs >> 16U) & 0170000U;
        const bool unixMode = host == 3 || host == 19;
        const bool directory = rawName.endsWith('/') || (attrs & 0x10U) != 0
            || (unixMode && kind == 0040000U);
        const bool symlink = unixMode && kind == 0120000U;
        const bool regular = !directory && !symlink && (!unixMode || kind == 0 || kind == 0100000U);
        if ((directory && (size != 0 || symlink || (unixMode && kind != 0 && kind != 0040000U)))
            || (!directory && !regular && !symlink)) {
            return reject(QStringLiteral("Symbolic links and unsupported ZIP entry types are not accepted."));
        }
        m_entries.append({name, static_cast<qint64>(size), crc, regular, directory, symlink,
                          static_cast<qsizetype>(dataOffset), static_cast<quint32>(compressed), method});
        ranges.append({loc, static_cast<qsizetype>(dataEnd)});
        at += headerSize;
    }
    if (at != end) {
        return reject(QStringLiteral("The ZIP directory count/size is inconsistent."));
    }
    std::sort(ranges.begin(), ranges.end());
    qsizetype previous = 0;
    for (const auto &range : ranges) {
        if (range.first != previous) {
            return reject(QStringLiteral("The ZIP contains overlapping entries, hidden data or a prefixed executable."));
        }
        previous = range.second;
    }
    if (static_cast<quint64>(previous) != directoryOffset) {
        return reject(QStringLiteral("The ZIP data does not end at its directory."));
    }
    return true;
}

QByteArray SafeZipReader::fileData(const QString &path) const
{
    if (!m_error.isEmpty()) {
        return {};
    }
    for (const auto &entry : m_entries) {
        if (entry.filePath != path || !entry.isFile) {
            continue;
        }
        if (entry.method == 0) {
            return m_bytes.mid(entry.dataOffset, entry.compressedSize);
        }
        QByteArray output(qMax<qsizetype>(1, static_cast<qsizetype>(entry.size)), Qt::Uninitialized);
        auto outputSize = static_cast<unsigned long>(entry.size);
        auto inputSize = static_cast<unsigned long>(entry.compressedSize);
        const int result = puff(reinterpret_cast<unsigned char *>(output.data()), &outputSize,
                                reinterpret_cast<const unsigned char *>(m_bytes.constData() + entry.dataOffset),
                                &inputSize);
        if (result != 0 || outputSize != static_cast<unsigned long>(entry.size)
            || inputSize != entry.compressedSize) {
            reject(QStringLiteral("The ZIP deflate stream is corrupt or exceeds its declared size."));
            return {};
        }
        output.resize(static_cast<qsizetype>(entry.size));
        return output;
    }
    reject(QStringLiteral("The ZIP file entry was not found."));
    return {};
}
