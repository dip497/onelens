import { configureStore } from '@reduxjs/toolkit';
import demandReducer from './demand/demandSlice';

const store = configureStore({
    reducer: {
        demand: demandReducer,
    },
});

export default store;
