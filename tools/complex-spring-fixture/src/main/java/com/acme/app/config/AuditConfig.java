package com.acme.app.config;

import com.acme.app.common.OrderStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Set;

/**
 * @Configuration with @Bean methods — exercises the @Bean method collector.
 * Each @Bean method should surface as a bean definition produced by this
 * configuration (the collector records the producing @Configuration + method).
 */
@Configuration
public class AuditConfig {

    @Bean
    public Set<OrderStatus> auditedStatuses() {
        return Set.of(OrderStatus.PAID, OrderStatus.SHIPPED);
    }

    @Bean
    public String auditTopic() {
        return "acme.orders.audit";
    }
}
