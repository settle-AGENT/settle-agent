package com.settleagent.backend.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

import java.util.List;

@Converter
public class StringListJsonConverter implements AttributeConverter<List<String>, String> {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {};

    @Override
    public String convertToDatabaseColumn(List<String> attribute) {
        if (attribute == null) {
            return null;
        }

        try {
            return OBJECT_MAPPER.writeValueAsString(attribute);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("accountPurposes를 JSON으로 변환할 수 없습니다.", exception);
        }
    }

    @Override
    public List<String> convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }

        try {
            return OBJECT_MAPPER.readValue(dbData, STRING_LIST);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("account_purposes JSON을 읽을 수 없습니다.", exception);
        }
    }
}
