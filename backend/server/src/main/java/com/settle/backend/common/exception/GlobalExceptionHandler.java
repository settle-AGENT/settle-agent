package com.settle.backend.common.exception;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(FeatureNotConfiguredException.class)
    public ResponseEntity<ErrorResponse> handleFeatureNotConfigured(
            FeatureNotConfiguredException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED)
                .body(new ErrorResponse("FEATURE_NOT_CONFIGURED", exception.getMessage()));
    }
}
