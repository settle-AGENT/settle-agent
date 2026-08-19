package com.settle.backend.domain.profile.client;

import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import java.util.Map;
import org.springframework.http.ResponseEntity;

public interface AiProfileClient {

    ResponseEntity<Map<String, Object>> confirm(ProfileConfirmRequest request);
}
