package com.onelens.springfix;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * @Configuration + @Bean — exercises the @Bean method collector. Should
 * surface as a CONFIGURATION bean with a greeterName bean method.
 */
@Configuration
public class Config {

    @Bean
    public String greeterName() {
        return "onelens";
    }
}
