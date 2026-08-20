package com.settle.backend.common.health;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Health", description = "서버 상태 확인")
public class HealthController {

    @GetMapping("/health")
    @Operation(summary = "Health check")
    @ApiResponse(responseCode = "200", description = "서버 정상",
            content = @Content(examples = @ExampleObject(value = """
                    {"status":"ok"}
                    """)))
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
