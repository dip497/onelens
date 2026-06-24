package com.acme.app.service;

import com.acme.app.common.OrderStatus;
import com.acme.app.domain.Customer;
import com.acme.app.domain.Order;
import com.acme.app.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Second @Service — exercises service-to-service composition: OrderService
 * depends on CustomerService (constructor injection) AND OrderRepository.
 * This creates a multi-hop dependency graph:
 *   OrderController -> OrderService -> CustomerService -> CustomerRepository
 *                              \------> OrderRepository
 * Plus CALL edges into the repositories and across services.
 */
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final CustomerService customerService;

    public OrderService(OrderRepository orderRepository, CustomerService customerService) {
        this.orderRepository = orderRepository;
        this.customerService = customerService;
    }

    @Transactional
    public Order placeOrder(String customerEmail, Double total) {
        Customer customer = customerService.findByEmail(customerEmail);
        Order order = new Order(customer, OrderStatus.PLACED, total);
        return orderRepository.save(order);
    }

    @Transactional(readOnly = true)
    public List<Order> findByStatus(OrderStatus status) {
        return orderRepository.findByStatus(status);
    }
}
