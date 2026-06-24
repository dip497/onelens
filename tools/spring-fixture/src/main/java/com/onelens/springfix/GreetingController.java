package com.onelens.springfix;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller — exercises the endpoint collector. The export should emit:
 *  - a REST_CONTROLLER bean
 *  - ENDPOINT nodes: GET /api/greetings/{name}, GET /api/greetings
 *  - an @Autowired dependency edge: GreetingController → GreetingService
 */
@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    private final GreetingService greetingService;

    @Autowired
    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping
    public String hello() {
        return greetingService.greet("world");
    }

    @GetMapping("/{name}")
    public String greetByName(@PathVariable String name) {
        return greetingService.greet(name);
    }
}
