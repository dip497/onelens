package com.onelens.springfix;

import org.springframework.stereotype.Service;

/**
 * Stereotype bean — exercises the bean collector. Should surface as a
 * SERVICE bean. greet() is called by GreetingController (call edge).
 */
@Service
public class GreetingService {

    public String greet(String name) {
        return "hello, " + name;
    }
}
