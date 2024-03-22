draft3 = {
    "$schema": "http://json-schema.org/draft-03/schema#",
    "dependencies": {
        "exclusiveMaximum": "maximum",
        "exclusiveMinimum": "minimum"
    },
    "id": "http://json-schema.org/draft-03/schema#",
    "properties": {
        "$ref": {
            "format": "uri",
            "type": "string"
        },
        "$schema": {
            "format": "uri",
            "type": "string"
        },
        "additionalItems": {
            "default": {},
            "type": [
                {
                    "$ref": "#"
                },
                "boolean"
            ]
        },
        "additionalProperties": {
            "default": {},
            "type": [
                {
                    "$ref": "#"
                },
                "boolean"
            ]
        },
        "default": {
            "type": "any"
        },
        "dependencies": {
            "additionalProperties": {
                "items": {
                    "type": "string"
                },
                "type": [
                    "string",
                    "array",
                    {
                        "$ref": "#"
                    }
                ]
            },
            "default": {},
            "type": [
                "string",
                "array",
                "object"
            ]
        },
        "description": {
            "type": "string"
        },
        "disallow": {
            "items": {
                "type": [
                    "string",
                    {
                        "$ref": "#"
                    }
                ]
            },
            "type": [
                "string",
                "array"
            ],
            "uniqueItems": True
        },
        "divisibleBy": {
            "default": 1,
            "exclusiveMinimum": True,
            "minimum": 0,
            "type": "number"
        },
        "enum": {
            "minItems": 1,
            "type": "array",
            "uniqueItems": True
        },
        "exclusiveMaximum": {
            "default": False,
            "type": "boolean"
        },
        "exclusiveMinimum": {
            "default": False,
            "type": "boolean"
        },
        "extends": {
            "default": {},
            "items": {
                "$ref": "#"
            },
            "type": [
                {
                    "$ref": "#"
                },
                "array"
            ]
        },
        "format": {
            "type": "string"
        },
        "id": {
            "format": "uri",
            "type": "string"
        },
        "items": {
            "default": {},
            "items": {
                "$ref": "#"
            },
            "type": [
                {
                    "$ref": "#"
                },
                "array"
            ]
        },
        "maxDecimal": {
            "minimum": 0,
            "type": "number"
        },
        "maxItems": {
            "minimum": 0,
            "type": "integer"
        },
        "maxLength": {
            "type": "integer"
        },
        "maximum": {
            "type": "number"
        },
        "minItems": {
            "default": 0,
            "minimum": 0,
            "type": "integer"
        },
        "minLength": {
            "default": 0,
            "minimum": 0,
            "type": "integer"
        },
        "minimum": {
            "type": "number"
        },
        "pattern": {
            "format": "regex",
            "type": "string"
        },
        "patternProperties": {
            "additionalProperties": {
                "$ref": "#"
            },
            "default": {},
            "type": "object"
        },
        "properties": {
            "additionalProperties": {
                "$ref": "#",
                "type": "object"
            },
            "default": {},
            "type": "object"
        },
        "required": {
            "default": False,
            "type": "boolean"
        },
        "title": {
            "type": "string"
        },
        "type": {
            "default": "any",
            "items": {
                "type": [
                    "string",
                    {
                        "$ref": "#"
                    }
                ]
            },
            "type": [
                "string",
                "array"
            ],
            "uniqueItems": True
        },
        "uniqueItems": {
            "default": False,
            "type": "boolean"
        }
    },
    "type": "object"
}
