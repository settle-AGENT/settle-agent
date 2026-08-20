package com.settle.backend.config;

import com.settle.backend.common.auth.CurrentMemberIdArgumentResolver;
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebMvcConfiguration implements WebMvcConfigurer {
    private final CurrentMemberIdArgumentResolver currentMemberIdArgumentResolver;

    public WebMvcConfiguration(CurrentMemberIdArgumentResolver currentMemberIdArgumentResolver) {
        this.currentMemberIdArgumentResolver = currentMemberIdArgumentResolver;
    }

    @Override
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(currentMemberIdArgumentResolver);
    }
}
