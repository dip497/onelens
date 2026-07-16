package com.acme.app.repository;

import com.acme.app.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

/**
 * Spring Data JPA repository — exercises JpaCollector's REPOSITORY_ROOTS
 * detection (extends JpaRepository) and the derived-query method scan
 * (findByEmail, existsByEmail). Should surface as a JPA REPOSITORY node
 * with entity type Customer and the derived queries.
 */
@Repository
public interface CustomerRepository extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    boolean existsByEmail(String email);
}
