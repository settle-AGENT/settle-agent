package com.settle.backend.common.exception;

import com.settle.backend.domain.profile.exception.ProfileValidationException;
import com.settle.backend.domain.auth.exception.EmailAlreadyExistsException;
import com.settle.backend.domain.auth.exception.InvalidCredentialsException;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

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

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleResourceNotFound(
            ResourceNotFoundException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse("RESOURCE_NOT_FOUND", exception.getMessage()));
    }

    @ExceptionHandler(DuplicateResourceException.class)
    public ResponseEntity<ErrorResponse> handleDuplicateResource(
            DuplicateResourceException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorResponse("DUPLICATE_RESOURCE", exception.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorResponse> handleIllegalArgument(
            IllegalArgumentException exception
    ) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse("INVALID_ARGUMENT", exception.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleRequestValidation(
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

        return ResponseEntity.unprocessableEntity()
                .body(new ErrorResponse("validation_failed", "요청 값을 확인해 주세요.", details));
    }

    @ExceptionHandler(ProfileValidationException.class)
    public ResponseEntity<ErrorResponse> handleProfileValidation(
            ProfileValidationException exception
    ) {
        return ResponseEntity.unprocessableEntity()
                .body(new ErrorResponse(
                        "validation_failed", exception.getMessage(), exception.getDetails()
                ));
    }

    @ExceptionHandler(FeatureNotConfiguredException.class)
    public ResponseEntity<ErrorResponse> handleFeatureNotConfigured(
            FeatureNotConfiguredException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED)
                .body(new ErrorResponse("FEATURE_NOT_CONFIGURED", exception.getMessage()));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ErrorResponse> handleResponseStatus(ResponseStatusException exception) {
        String error = exception.getReason() == null ? "internal" : exception.getReason();
        return ResponseEntity.status(exception.getStatusCode())
                .body(new ErrorResponse(error, error));
    }
}
