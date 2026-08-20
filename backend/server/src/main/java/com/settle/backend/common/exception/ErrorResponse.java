package com.settle.backend.common.exception;

public record ErrorResponse(Detail detail) {
    public ErrorResponse(String error, String message) {
        this(new Detail(error, message, null));
    }

    public ErrorResponse(String error, String message, Object details) {
        this(new Detail(error, message, details));
    }

    public record Detail(String error, String message, Object details) {
    }
}
