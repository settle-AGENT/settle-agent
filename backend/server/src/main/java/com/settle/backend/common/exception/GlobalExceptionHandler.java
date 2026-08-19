package com.settle.backend.common.exception;

import com.settle.backend.domain.profile.exception.ProfileValidationException;
import com.settle.backend.domain.auth.exception.EmailAlreadyExistsException;
import com.settle.backend.domain.auth.exception.InvalidCredentialsException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(EmailAlreadyExistsException.class)
    public ResponseEntity<ErrorResponse> handleEmailAlreadyExists(
            EmailAlreadyExistsException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorResponse("EMAIL_ALREADY_EXISTS", exception.getMessage()));
    }

    @ExceptionHandler(InvalidCredentialsException.class)
    public ResponseEntity<ErrorResponse> handleInvalidCredentials(
            InvalidCredentialsException exception
    ) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(new ErrorResponse("INVALID_CREDENTIALS", exception.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleRequestValidation(
            MethodArgumentNotValidException exception
    ) {
        List<Map<String, String>> details = exception.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "reason", error.getDefaultMessage() == null
                                ? "invalid_value"
                                : error.getDefaultMessage()
                ))
                .toList();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", "validation_failed");
        body.put("message", "요청 값을 확인해 주세요.");
        body.put("details", details);
        return ResponseEntity.unprocessableEntity().body(body);
    }

    @ExceptionHandler(ProfileValidationException.class)
    public ResponseEntity<Map<String, Object>> handleProfileValidation(
            ProfileValidationException exception
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", "validation_failed");
        body.put("message", exception.getMessage());
        body.put("details", exception.getDetails());
        return ResponseEntity.unprocessableEntity().body(body);
    }

    @ExceptionHandler(FeatureNotConfiguredException.class)
    public ResponseEntity<ErrorResponse> handleFeatureNotConfigured(
            FeatureNotConfiguredException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED)
                .body(new ErrorResponse("FEATURE_NOT_CONFIGURED", exception.getMessage()));
    }
}
