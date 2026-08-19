package com.settle.backend.domain.file.repository;

import com.settle.backend.domain.file.entity.UploadTicket;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryUploadRepository implements UploadRepository {
    private final ConcurrentHashMap<UUID, UploadTicket> uploads = new ConcurrentHashMap<>();

    @Override
    public UploadTicket save(UploadTicket upload) {
        uploads.put(upload.id(), upload);
        return upload;
    }

    @Override
    public Optional<UploadTicket> findById(UUID uploadId) {
        return Optional.ofNullable(uploads.get(uploadId));
    }
}
