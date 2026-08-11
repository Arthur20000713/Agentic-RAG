package com.livestock.platform.security;

import java.time.Clock;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableMethodSecurity
@EnableConfigurationProperties(SecurityProperties.class)
public class SecurityConfig {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock securityClock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    JwtService jwtService(SecurityProperties properties, Clock securityClock) {
        return new JwtService(properties, securityClock);
    }

    @Bean
    RedisRefreshTokenFamilyStore refreshTokenFamilyStore(
            StringRedisTemplate redis,
            SecurityProperties properties
    ) {
        return new RedisRefreshTokenFamilyStore(redis, properties);
    }

    @Bean
    @ConditionalOnMissingBean(UserSecurityReader.class)
    UserSecurityReader denyAllUserSecurityReader() {
        return userId -> java.util.Optional.empty();
    }

    @Bean
    JwtAuthenticationFilter jwtAuthenticationFilter(
            JwtService jwtService,
            RedisRefreshTokenFamilyStore refreshTokenStore,
            UserSecurityReader userSecurityReader,
            ApiAuthenticationEntryPoint authenticationEntryPoint,
            SecurityErrorWriter errorWriter
    ) {
        return new JwtAuthenticationFilter(
                jwtService,
                refreshTokenStore,
                userSecurityReader,
                authenticationEntryPoint,
                errorWriter
        );
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(SecurityProperties properties) {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(properties.corsAllowedOrigins());
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "X-Request-ID"
        ));
        configuration.setExposedHeaders(List.of(
                "X-Request-ID",
                "Idempotent-Replayed",
                "Location"
        ));
        configuration.setAllowCredentials(false);
        configuration.setMaxAge(3600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationFilter jwtAuthenticationFilter,
            ApiAuthenticationEntryPoint authenticationEntryPoint,
            ApiAccessDeniedHandler accessDeniedHandler,
            CorsConfigurationSource corsConfigurationSource
    ) throws Exception {
        http
                .cors(cors -> cors.configurationSource(corsConfigurationSource))
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(
                        SessionCreationPolicy.STATELESS
                ))
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(authenticationEntryPoint)
                        .accessDeniedHandler(accessDeniedHandler)
                )
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .requestMatchers("/actuator/prometheus")
                        .hasAuthority("AUDIT_READ")
                        .requestMatchers(
                                "/",
                                "/index.html",
                                "/styles.css",
                                "/app.js",
                                "/actuator/health/liveness",
                                "/actuator/health/readiness",
                                "/api/v1/auth/login",
                                "/api/v1/auth/refresh"
                        ).permitAll()
                        .anyRequest().authenticated()
                )
                .addFilterBefore(
                        jwtAuthenticationFilter,
                        UsernamePasswordAuthenticationFilter.class
                );
        return http.build();
    }
}
