package com.livestock.platform.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Locale;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.dao.DataAccessException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.web.filter.OncePerRequestFilter;

public final class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String BEARER_PREFIX = "bearer ";

    private final JwtService jwtService;
    private final RedisRefreshTokenFamilyStore refreshTokenStore;
    private final UserSecurityReader userSecurityReader;
    private final ApiAuthenticationEntryPoint authenticationEntryPoint;
    private final SecurityErrorWriter errorWriter;

    public JwtAuthenticationFilter(
            JwtService jwtService,
            RedisRefreshTokenFamilyStore refreshTokenStore,
            UserSecurityReader userSecurityReader,
            ApiAuthenticationEntryPoint authenticationEntryPoint,
            SecurityErrorWriter errorWriter
    ) {
        this.jwtService = jwtService;
        this.refreshTokenStore = refreshTokenStore;
        this.userSecurityReader = userSecurityReader;
        this.authenticationEntryPoint = authenticationEntryPoint;
        this.errorWriter = errorWriter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String authorization = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (authorization == null && SecurityContextHolder.getContext().getAuthentication() == null) {
            filterChain.doFilter(request, response);
            return;
        }
        if (SecurityContextHolder.getContext().getAuthentication() != null) {
            filterChain.doFilter(request, response);
            return;
        }

        try {
            String token = bearerToken(authorization);
            JwtService.DecodedAccessToken accessToken = jwtService.decodeAccessToken(token);
            if (!refreshTokenStore.isFamilyActive(accessToken.sessionId())) {
                reject(request, response);
                return;
            }
            UserPrincipal principal = userSecurityReader.findActiveUser(accessToken.userId())
                    .filter(user -> user.securityVersion() == accessToken.securityVersion())
                    .orElseThrow(() -> new BadCredentialsException("Invalid access token"));
            var authorities = principal.authorities().stream()
                    .map(SimpleGrantedAuthority::new)
                    .toList();
            UsernamePasswordAuthenticationToken authentication =
                    new UsernamePasswordAuthenticationToken(principal, null, authorities);
            authentication.setDetails(
                    new WebAuthenticationDetailsSource().buildDetails(request)
            );
            SecurityContextHolder.getContext().setAuthentication(authentication);
            filterChain.doFilter(request, response);
        } catch (SecurityStateUnavailableException exception) {
            SecurityContextHolder.clearContext();
            errorWriter.write(
                    response,
                    HttpStatus.SERVICE_UNAVAILABLE.value(),
                    "AUTH_STATE_UNAVAILABLE",
                    "Authentication state is temporarily unavailable"
            );
        } catch (DataAccessException | CannotCreateTransactionException exception) {
            SecurityContextHolder.clearContext();
            errorWriter.write(
                    response,
                    HttpStatus.SERVICE_UNAVAILABLE.value(),
                    "DATASTORE_UNAVAILABLE",
                    "Business data is temporarily unavailable"
            );
        } catch (JwtException | BadCredentialsException | IllegalArgumentException exception) {
            SecurityContextHolder.clearContext();
            reject(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private String bearerToken(String authorization) {
        if (authorization == null
                || !authorization.toLowerCase(Locale.ROOT).startsWith(BEARER_PREFIX)) {
            throw new BadCredentialsException("Invalid authorization scheme");
        }
        String token = authorization.substring(BEARER_PREFIX.length()).trim();
        if (token.isEmpty() || token.contains(" ")) {
            throw new BadCredentialsException("Invalid bearer token");
        }
        return token;
    }

    private void reject(HttpServletRequest request, HttpServletResponse response)
            throws IOException, ServletException {
        authenticationEntryPoint.commence(
                request,
                response,
                new BadCredentialsException("Invalid access token")
        );
    }
}
