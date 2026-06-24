package com.acme.app.domain;

import com.acme.app.common.OrderStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

/**
 * Second @Entity — exercises @ManyToOne + @JoinColumn (a JPA relation edge),
 * @Enumerated on the OrderStatus enum, and the EXTENDS edge to AbstractEntity.
 * The relation Order -> Customer should surface as a JPA relationship.
 */
@Entity
@Table(name = "orders")
public class Order extends AbstractEntity {

    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Double total;

    public Order() {}

    public Order(Customer customer, OrderStatus status, Double total) {
        this.customer = customer;
        this.status = status;
        this.total = total;
    }

    public Customer getCustomer() { return customer; }
    public void setCustomer(Customer customer) { this.customer = customer; }

    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }

    public Double getTotal() { return total; }
    public void setTotal(Double total) { this.total = total; }
}
