package com.livestock.platform;

import com.livestock.platform.ai.AiServiceProperties;
import com.livestock.platform.knowledge.KnowledgeProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication(exclude = UserDetailsServiceAutoConfiguration.class)
@EnableScheduling
@EnableConfigurationProperties({AiServiceProperties.class, KnowledgeProperties.class})
public class LivestockBusinessApplication {

    public static void main(String[] args) {
        SpringApplication.run(LivestockBusinessApplication.class, args);
    }
}
