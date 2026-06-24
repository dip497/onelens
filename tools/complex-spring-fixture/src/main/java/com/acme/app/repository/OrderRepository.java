package com.acme.app.repository;

import com.acme.app.common.OrderStatus;
import com.acme.app.domain.Order;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * Second repository — extends JpaRepository<Order, Long>. The derived query
 * findByStatusAndCustomerName would be a more complex one; keep it simple
 * with findByStatus so the derived-query scan finds it. IMPLEMENTS edge to
 * JpaRepository via the inheritance collector.
 */
@Repository
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    long countByStatus(OrderStatus status);
}
