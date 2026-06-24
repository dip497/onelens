package com.acme.app.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

/**
 * JPA @Entity — exercises the JpaCollector: @Entity, @Table(name="customers"),
 * @Column fields. Should surface as a JPA entity node with tableName and
 * column metadata. Extends AbstractEntity (EXTENDS edge).
 */
@Entity
@Table(name = "customers")
public class Customer extends AbstractEntity {

    @Column(nullable = false)
    private String name;

    @Column(unique = true, nullable = false)
    private String email;

    public Customer() {}

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
