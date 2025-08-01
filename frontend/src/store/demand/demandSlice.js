import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

const API_URL = 'http://10.20.40.217:5000/api/features'; // Replace with your actual API

// Thunks for CRUD
export const fetchDemands = createAsyncThunk('demand/fetchAll', async () => {
    const response = await axios.get(API_URL);
    return response.data;
});

export const fetchDemand = createAsyncThunk('demand/fetchOne', async (id) => {
    const response = await axios.get(`${API_URL}/${id}`);
    return response.data;
});

export const createDemand = createAsyncThunk('demand/create', async (data) => {
    const response = await axios.post(API_URL, data);
    return response.data;
});

export const updateDemand = createAsyncThunk('demand/update', async ({ id, ...patch }) => {
    const response = await axios.put(`${API_URL}/${id}`, patch);
    return response.data;
});

export const deleteDemand = createAsyncThunk('demand/delete', async (id) => {
    await axios.delete(`${API_URL}/${id}`);
    return id;
});

const demandSlice = createSlice({
    name: 'demand',
    initialState: {
        list: [],
        current: null,
        loading: false,
        error: null,
    },
    reducers: {},

    extraReducers: (builder) => {
        builder
            .addCase(fetchDemands.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchDemands.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload;
            })
            .addCase(fetchDemands.rejected, (state, action) => {
                state.loading = false;
                state.error = action.error.message;
            })

            .addCase(createDemand.fulfilled, (state, action) => {
                state.list.push(action.payload);
            })

            .addCase(updateDemand.fulfilled, (state, action) => {
                const index = state.list.findIndex((d) => d.id === action.payload.id);
                if (index !== -1) {
                    state.list[index] = action.payload;
                }
            })

            .addCase(deleteDemand.fulfilled, (state, action) => {
                state.list = state.list.filter((d) => d.id !== action.payload);
            });
    },
});

export default demandSlice.reducer;
