package com.settle.backend.domain.profile.controller;

import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import com.settle.backend.domain.profile.service.ProfileService;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {
    private final ProfileService profileService;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @PostMapping("/confirm")
    public ResponseEntity<Map<String, Object>> confirm(
            @Valid @RequestBody ProfileConfirmRequest request
    ) {
        return profileService.confirm(request);
    }
}
