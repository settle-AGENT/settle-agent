package com.settle.backend.domain.file.repository;

import com.settle.backend.domain.file.entity.UploadTicket;
import java.util.Optional;
import java.util.UUID;

public interface UploadRepository {
    UploadTicket save(UploadTicket upload);

    Optional<UploadTicket> findById(UUID uploadId);
}
