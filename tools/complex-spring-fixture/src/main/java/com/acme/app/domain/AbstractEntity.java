package com.acme.app.domain;

import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

/**
 * @MappedSuperclass base — exercises INHERITANCE (EXTENDS edges from the
 * concrete entities) and the @Id detection that the JPA collector attributes
 * to subclasses. OneLens should emit an EXTENDS edge Customer → AbstractEntity
 * and Order → AbstractEntity.
 */
@MappedSuperclass
public abstract class AbstractEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }
}
