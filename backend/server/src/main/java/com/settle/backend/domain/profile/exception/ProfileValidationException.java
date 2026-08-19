package com.settle.backend.domain.profile.exception;

import java.util.List;
import java.util.Map;

public class ProfileValidationException extends RuntimeException {
    private final List<Map<String, String>> details;

    public ProfileValidationException(String message, List<Map<String, String>> details) {
        super(message);
        this.details = details;
    }

    public List<Map<String, String>> getDetails() {
        return details;
    }
}
