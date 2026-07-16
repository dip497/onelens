package com.acme.app.service;

import com.acme.app.domain.Customer;
import com.acme.app.repository.CustomerRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * @Service bean with constructor injection of CustomerRepository. Exercises:
 *  - SERVICE bean detection
 *  - @Autowired-equivalent (single-constructor injection) edge to CustomerRepository
 *  - CALL edges: findAll -> repository.findAll, create -> repository.save
 */
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Customer> findAll() {
        return repository.findAll();
    }

    @Transactional
    public Customer create(String name, String email) {
        if (repository.existsByEmail(email)) {
            throw new IllegalArgumentException("email already in use: " + email);
        }
        return repository.save(new Customer(name, email));
    }

    @Transactional(readOnly = true)
    public Customer findByEmail(String email) {
        return repository.findByEmail(email)
            .orElseThrow(() -> new IllegalArgumentException("no customer: " + email));
    }
}
